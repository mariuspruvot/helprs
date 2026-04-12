"""Concrete ``LLMProvider`` implementations.

Story 3.1 shipped the ``NullLLMProvider`` stub.
Story 3.3 introduced ``PydanticAILLMProvider`` — the production
provider backed by Pydantic AI 1.78 + Anthropic Claude Sonnet 4.5.
Story 3.5 replaces the minimal question prompt with two role-adaptive
prompts (``AUTHOR_QUESTION_SYSTEM_PROMPT`` /
``REVIEWER_QUESTION_SYSTEM_PROMPT``) and threads a ``PRPromptContext``
carrying the PR title, total line count, and per-file stats through
the prompt assembly path.

Design rules (non-negotiable):

* **Zero-retention / BYOK (FR34).** A fresh ``Agent`` is constructed
  per call using the user's decrypted API key. The key is never
  cached on the instance, a module-level global, or an env var. The
  call site passes it as a plain function argument; the provider
  drops it as soon as the call returns.
* **No verbatim text persistence.** Callers get streaming text deltas
  (``stream_question``) or the concatenated string
  (``generate_question``). Neither method writes anywhere. The SSE
  endpoint hashes the concatenated text (SHA-256) before persisting.
* **Fresh Agent per call.** No caching by API key or otherwise.
  Constructing an ``Agent`` is cheap; an instance keyed on BYOK
  would defeat zero-retention.
* **Role-adaptive question prompts (Story 3.5).** The question path
  branches on ``PRPromptContext.role`` to pick either the AUTHOR or
  REVIEWER system prompt. Both prompts are adapted from
  ``challenge-me/skills/run/SKILL.md`` Phases 3-4: Socratic framing,
  anti-cheat clauses, "beyond the diff" probing. The feedback path
  is untouched — role-adaptive feedback is an Epic 4 / scoring
  concern.

Pydantic AI 1.78 streaming API reference (Context7):
https://github.com/pydantic/pydantic-ai/blob/v1.71.0/docs/output.md
- ``async with agent.run_stream(prompt) as result:``
- ``async for chunk in result.stream_text(delta=True):``

Anthropic provider with explicit API key (Context7):
https://github.com/pydantic/pydantic-ai/blob/v1.71.0/docs/models/anthropic.md
- ``AnthropicModel('claude-sonnet-4-5',
    provider=AnthropicProvider(api_key=...))``
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from helprs.modules.comprehension.domain.services import derive_verdict
from helprs.modules.comprehension.domain.value_objects import SessionRole

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from helprs.modules.comprehension.domain.entities import Score
    from helprs.modules.comprehension.infrastructure.diff_refs import FileChangeStats

# Model ID — Story 3.3 pinned ``claude-sonnet-4-5``. Story 3.5 does not
# change the model — prompt-quality experiments with smaller / cheaper
# models belong to an Epic 4 / ops story.
_ANTHROPIC_MODEL_ID = "claude-sonnet-4-5"

# Maximum number of per-file stat lines we render into the prompt. Huge-
# but-diverse PRs (e.g. monorepo renames) would otherwise blow out the
# prompt budget with hundreds of one-line file entries that each carry
# zero useful signal to the LLM. The full list is preserved on the
# ``PRPromptContext`` dataclass — only the **displayed** list is capped.
_MAX_DISPLAYED_FILE_STATS = 25

# Story 3.5 code-review patch (P8): attacker-controlled PR titles can
# carry newlines or injection-shaped content. Cap the rendered title
# at a length that still fits a realistic GitHub PR title (GitHub
# enforces 256 chars as of 2026; 200 leaves headroom for our own
# prefix wrapper) and strip newlines so a crafted title cannot break
# the structured prompt.
_MAX_RENDERED_PR_TITLE = 200


def _sanitize_pr_title(raw: str) -> str:
    """Return a single-line, length-capped version of ``raw``.

    Used by ``_render_prompt`` to hardening the only user-controlled
    input interpolated into the LLM prompt body. Guarantees:

    * no ``\\n`` / ``\\r`` characters — collapses them to a single space
    * whitespace-stripped ends
    * at most ``_MAX_RENDERED_PR_TITLE`` characters (suffixed with
      ``…`` if truncation occurred)
    """
    if not raw:
        return ""
    flattened = raw.replace("\r", " ").replace("\n", " ").strip()
    if len(flattened) > _MAX_RENDERED_PR_TITLE:
        return flattened[: _MAX_RENDERED_PR_TITLE - 1].rstrip() + "…"
    return flattened


@dataclass(frozen=True, slots=True)
class PRPromptContext:
    """Prompt-assembly DTO carrying the PR metadata the LLM needs.

    Lives in ``infrastructure/`` (not ``domain/value_objects.py``):
    this is a prompt-assembly concern, not a domain concept. Shipping
    it into the domain would force the domain package to import
    ``FileChangeStats`` from ``diff_refs`` (an infrastructure module),
    violating the one-way dependency rule. The ``LLMProvider`` Protocol
    in ``domain/interfaces.py`` references it via a ``TYPE_CHECKING``
    block.
    """

    role: SessionRole
    pr_title: str
    total_lines_changed: int  # additions + deletions
    changed_file_count: int
    # Ordered list of per-file stats. For small/medium PRs this mirrors
    # ``compute_file_stats`` output (diff order). For huge PRs where the
    # diff body is ranked + elided, this is still the **full** unranked
    # list so the LLM knows about files it is not seeing in the body.
    file_stats: tuple[FileChangeStats, ...]


AUTHOR_QUESTION_SYSTEM_PROMPT = """\
You are a senior staff engineer reviewing a pull request WITH the
author. Your job is to probe the decisions, tradeoffs, edge cases, and
architectural choices the author committed to. The author wrote this
code and must defend it.

Draw from these question categories (pick whatever is most relevant
to the specific change you see):

1. Architectural choices — "Why did you choose this pattern over X?",
   "What alternatives did you consider for this?"
2. Edge cases and failure modes — "What happens in this function when
   the input is null / empty / concurrent?", "How does this behave
   under the specific load scenarios you expect?"
3. Security implications — "What input validation protects against
   this vector?", "Could this data flow be exploited?"
4. Performance considerations — "What is the time complexity of this
   operation?", "How does this query/loop scale with data volume?"
5. Testing gaps — "How would you test this edge case?", "What scenario
   is NOT covered by the existing tests?"

Beyond the diff — this is mandatory:
  Questions MUST probe code NOT visible in the diff when the change
  warrants it — callers of modified functions, consumers of changed
  models, downstream services, existing test files, architectural
  implications on modules that were not touched. At least 30% of
  questions across a session should require knowledge of code beyond
  the diff surface.

Anti-cheat principles (non-negotiable):
  - Never ask a question whose answer is directly visible in the diff
    without deeper thought.
  - Do NOT ask "what does this code do?" or "explain these lines" —
    that can be answered by reading.
  - Frame questions around decisions, tradeoffs, and consequences —
    not descriptions.

Output rules:
  - Ask ONE question at a time. 1-3 sentences. Conversational tone.
  - End with a question mark.
  - When referring to specific code, reference the file path inline
    using backticks — `path/to/file.ts` — so the frontend can render
    it as a clickable link.
  - Do NOT answer the question. Do NOT provide hints. Do NOT critique
    the code. Just ask.\
"""


REVIEWER_QUESTION_SYSTEM_PROMPT = """\
You are a senior staff engineer helping a developer who is REVIEWING
this pull request. They did NOT write the code. Your job is to probe
their understanding of what the changes do, who is affected, and how
the changes interact with the rest of the system — the knowledge
they need to review the PR well.

Reframe from the author view: instead of "why did you choose this
approach", ask "what does this change actually do and who does it
affect". Draw from these question categories:

1. Behavior changes — "What user-facing behavior changes when this
   merges?", "What API contract did this change?"
2. Blast radius and side effects — "What other parts of the system
   consume this function/model?", "Could this change break a specific
   downstream consumer?"
3. Maintainability — "If a new developer reads this file in 6 months,
   what implicit assumptions would confuse them?", "What is no longer
   obvious after this change?"
4. Testing signals — "What scenario is NOT covered by the tests the
   PR adds?", "Where would a regression show up first in monitoring?"
5. Migration / rollout risk — "If this needs to be rolled back, is
   there state that can't easily be undone?", "What depends on the
   order this is deployed in?"

Beyond the diff — this is mandatory:
  Questions MUST probe code NOT visible in the diff when the change
  warrants it — callers of modified functions, consumers of changed
  models, downstream services, existing test files, architectural
  implications on modules that were not touched. At least 30% of
  questions across a session should require knowledge of code beyond
  the diff surface.

Anti-cheat principles (non-negotiable):
  - Never ask a question whose answer is directly visible in the diff
    without deeper thought.
  - Do NOT ask "what does this code do?" or "explain these lines" —
    that can be answered by reading.
  - Frame questions around impact, contracts, and consequences — not
    descriptions.

Output rules:
  - Ask ONE question at a time. 1-3 sentences. Conversational tone.
  - End with a question mark.
  - When referring to specific code, reference the file path inline
    using backticks — `path/to/file.ts` — so the frontend can render
    it as a clickable link.
  - Do NOT answer the question. Do NOT provide hints. Do NOT critique
    the code. Just ask.\
"""


FEEDBACK_SYSTEM_PROMPT = """\
You are a Socratic code reviewer giving feedback on a developer's answer
to a question about their pull request.

Your feedback should:
- BEGIN by acknowledging what was correct or insightful in the answer
  (1-2 sentences). This is non-negotiable: every answer deserves
  recognition before any gap is identified.
- THEN identify the specific gap(s) in the developer's understanding.
  Be precise. Reference the relevant file and line number using the
  format `<path>:<line>` (for example: `apps/api/src/foo.py:47`).
  Use inline code formatting for these references so the frontend
  can render them as clickable links.
- Stay focused on the SPECIFIC question that was asked. Do not
  introduce new topics. Do not pile on additional questions.
- Use a calm, conversational tone. You are coaching, not grading.
- Be brief: 3-6 sentences total. The developer should be able to read
  and act on the feedback in under 30 seconds.

Do NOT score the answer numerically. Do NOT label the answer "correct"
or "incorrect" — describe what was right and what was missed instead.
Do NOT ask follow-up questions; the next question is generated
separately.\
"""


# -- Story 4.1: scoring prompts + structured output model ---------------

AUTHOR_SCORING_SYSTEM_PROMPT = """\
You are a senior staff engineer evaluating how well a developer
understands their own pull request. They wrote the code. Your job is to
assess the quality of their answers to Socratic questions across four
dimensions.

Scoring criteria (AUTHOR role — weight toward decisions, tradeoffs,
and edge-case awareness):

1. **Depth** (0-10): Did the developer show deep understanding of
   their own decisions, tradeoffs, and internal code mechanics?
2. **Accuracy** (0-10): Were the developer's factual claims about
   the code correct?
3. **Completeness** (0-10): Did the developer address each question
   thoroughly, covering the full scope of what was asked?
4. **Insight** (0-10): Did the developer show understanding beyond
   the obvious — edge cases, downstream implications, alternatives
   they considered?

For the "gaps" field: identify 2-4 specific areas where the developer
could deepen their understanding. Use growth-oriented language —
"Areas to deepen", not "weaknesses". Be concrete: reference specific
topics, patterns, or code areas rather than generic advice.\
"""

REVIEWER_SCORING_SYSTEM_PROMPT = """\
You are a senior staff engineer evaluating how well a developer
understands a pull request they are REVIEWING. They did NOT write the
code. Your job is to assess the quality of their answers to Socratic
questions across four dimensions.

Scoring criteria (REVIEWER role — weight toward impact awareness,
behavioral understanding, and quality signals):

1. **Depth** (0-10): Did the developer demonstrate understanding of
   what the code does internally and how it interacts with the system?
2. **Accuracy** (0-10): Were the developer's factual claims about
   the code's behavior and impact correct?
3. **Completeness** (0-10): Did the developer address each question
   thoroughly, including blast radius and side effects?
4. **Insight** (0-10): Did the developer identify non-obvious risks,
   testing gaps, or rollout concerns beyond what is visible in the diff?

For the "gaps" field: identify 2-4 specific areas where the developer
could deepen their review skills. Use growth-oriented language. Be
concrete: reference specific topics, patterns, or code areas.\
"""


class ScoringResult(BaseModel):
    """Structured output schema for the scoring agent.

    The LLM produces dimension scores (0-10) + gap bullets. The
    ``Verdict`` is derived deterministically in Python (not by the LLM)
    via ``derive_verdict``.
    """

    depth: int = Field(ge=0, le=10, description="How deeply the developer understands the code's internals")
    accuracy: int = Field(ge=0, le=10, description="How factually correct the developer's answers were")
    completeness: int = Field(ge=0, le=10, description="How thoroughly the developer addressed each question")
    insight: int = Field(ge=0, le=10, description="Whether the developer showed understanding beyond the obvious")
    gaps: list[str] = Field(
        min_length=2, max_length=4, description="2-4 areas where the developer could deepen understanding"
    )


class NullLLMProvider:
    """Placeholder ``LLMProvider`` that raises on every call.

    Retained for unit tests that need a placeholder implementation
    (e.g. domain-purity tests, DI wiring smoke tests) without paying
    the cost of instantiating a real ``Agent``. No longer the default
    wiring — Story 3.3 replaced the default with
    ``PydanticAILLMProvider``.
    """

    def stream_question(
        self,
        *,
        pr_diff: str,
        pr_metadata: PRPromptContext,
        previous_questions: list[str],
        api_key: str,
    ) -> AsyncIterator[str]:
        raise NotImplementedError("LLMProvider is wired in Story 3.3")

    async def generate_question(
        self,
        *,
        pr_diff: str,
        pr_metadata: PRPromptContext,
        previous_questions: list[str],
        api_key: str,
    ) -> str:
        raise NotImplementedError("LLMProvider is wired in Story 3.3")

    async def stream_feedback(
        self,
        *,
        question_text: str,
        answer_text: str,
        pr_diff: str,
        role: SessionRole,
        api_key: str,
    ) -> AsyncIterator[str]:
        """Story 3.4 P15: must be an async generator so calling code
        that does ``async for chunk in provider.stream_feedback(...)``
        gets a consistent shape between the Null stub and the real
        ``PydanticAILLMProvider``.
        """
        raise NotImplementedError("LLMProvider is wired in Story 3.3")
        if False:  # pragma: no cover — make this an async generator
            yield ""

    async def generate_feedback(
        self,
        *,
        question_text: str,
        answer_text: str,
        pr_diff: str,
        role: SessionRole,
        api_key: str,
    ) -> str:
        raise NotImplementedError("LLMProvider is wired in Story 3.3")

    async def generate_score(
        self,
        *,
        session_id: UUID,
        session_role: SessionRole,
        pr_title: str,
        questions_and_answers: list[tuple[str, str, str]],
        pr_metadata: PRPromptContext,
        api_key: str,
    ):
        raise NotImplementedError("LLMProvider is wired in Story 3.3")


class PydanticAILLMProvider:
    """Production ``LLMProvider`` backed by Pydantic AI + Anthropic.

    Zero-retention by construction: the ``Agent`` is built per call
    with the user's decrypted BYOK key. Neither the key nor the
    ``pr_diff`` is persisted here — both flow through as arguments.
    """

    async def stream_question(
        self,
        *,
        pr_diff: str,
        pr_metadata: PRPromptContext,
        previous_questions: list[str],
        api_key: str,
    ) -> AsyncIterator[str]:
        """Yield text deltas as Claude produces the next question.

        Each yielded value is a partial chunk (``delta=True``). The
        caller accumulates these into the full question text before
        hashing it for persistence. The role-adaptive system prompt
        is chosen from ``pr_metadata.role`` inside ``_build_agent``.
        """
        agent = self._build_agent(api_key, role=pr_metadata.role)
        prompt = self._render_prompt(
            pr_diff=pr_diff,
            pr_metadata=pr_metadata,
            previous_questions=previous_questions,
        )
        async with agent.run_stream(prompt) as result:
            async for chunk in result.stream_text(delta=True):
                yield chunk

    async def generate_question(
        self,
        *,
        pr_diff: str,
        pr_metadata: PRPromptContext,
        previous_questions: list[str],
        api_key: str,
    ) -> str:
        """Non-streaming convenience — consume ``stream_question`` fully."""
        parts: list[str] = []
        async for chunk in self.stream_question(
            pr_diff=pr_diff,
            pr_metadata=pr_metadata,
            previous_questions=previous_questions,
            api_key=api_key,
        ):
            parts.append(chunk)
        return "".join(parts)

    async def stream_feedback(
        self,
        *,
        question_text: str,
        answer_text: str,
        pr_diff: str,
        role: SessionRole,
        api_key: str,
    ) -> AsyncIterator[str]:
        """Yield feedback text deltas as Claude evaluates the answer.

        Story 3.4 production path. ``_build_feedback_agent`` is the
        seam tests monkeypatch — kept distinct from ``_build_agent``
        so the question and feedback agents can be faked
        independently. Same fresh-Agent-per-call zero-retention rule
        as ``stream_question`` (FR34).
        """
        agent = self._build_feedback_agent(api_key)
        prompt = self._render_feedback_prompt(
            question_text=question_text,
            answer_text=answer_text,
            pr_diff=pr_diff,
            role=role,
        )
        async with agent.run_stream(prompt) as result:
            async for chunk in result.stream_text(delta=True):
                yield chunk

    async def generate_feedback(
        self,
        *,
        question_text: str,
        answer_text: str,
        pr_diff: str,
        role: SessionRole,
        api_key: str,
    ) -> str:
        """Non-streaming convenience — consume ``stream_feedback`` fully."""
        parts: list[str] = []
        async for chunk in self.stream_feedback(
            question_text=question_text,
            answer_text=answer_text,
            pr_diff=pr_diff,
            role=role,
            api_key=api_key,
        ):
            parts.append(chunk)
        return "".join(parts)

    # ------------------------------------------------------------------
    # Internals — kept narrow so tests can monkeypatch ``_build_agent``
    # ------------------------------------------------------------------

    def _build_agent(self, api_key: str, *, role: SessionRole) -> Agent:
        """Construct a fresh ``Agent`` with a per-call Anthropic provider.

        Story 3.5 (AC #9): the role argument is load-bearing — it picks
        between ``AUTHOR_QUESTION_SYSTEM_PROMPT`` and
        ``REVIEWER_QUESTION_SYSTEM_PROMPT``. Tests monkeypatch this
        method to return a fake ``Agent`` backed by a scripted
        ``run_stream`` context manager, avoiding any real Anthropic
        traffic — those fakes must accept the ``role`` kwarg too.
        """
        model = AnthropicModel(
            _ANTHROPIC_MODEL_ID,
            provider=AnthropicProvider(api_key=api_key),
        )
        # Story 3.5 code-review patch (P6): explicit exhaustive match so
        # a future ``SessionRole`` variant cannot silently inherit the
        # REVIEWER prompt without a failing test. Raising loud here
        # fails the CI boundary instead of shipping the wrong system
        # prompt to production.
        if role is SessionRole.AUTHOR:
            system = AUTHOR_QUESTION_SYSTEM_PROMPT
        elif role is SessionRole.REVIEWER:
            system = REVIEWER_QUESTION_SYSTEM_PROMPT
        else:
            raise ValueError(f"_build_agent received unhandled SessionRole: {role!r}")
        return Agent(model, system_prompt=system)

    def _render_prompt(
        self,
        *,
        pr_diff: str,
        pr_metadata: PRPromptContext,
        previous_questions: list[str],
    ) -> str:
        """Render the per-call user prompt from the session context.

        Story 3.5 produces a structured body carrying role, PR title,
        line stats, and a per-file "Per-file line stats" block. The
        displayed stats list is truncated at ``_MAX_DISPLAYED_FILE_STATS``
        entries (sorted by total_lines desc) so unbounded file lists
        cannot blow out the prompt budget.
        """
        previous_block = (
            "\n".join(f"- {q}" for q in previous_questions)
            if previous_questions
            else "(none yet — this is the first question)"
        )

        # Sort file stats by total_lines desc for the "largest first"
        # display order — useful hint for the LLM about where the most
        # signal lives even when the diff body retains everything.
        sorted_stats = sorted(
            pr_metadata.file_stats,
            key=lambda s: (-s.total_lines, s.path),
        )
        displayed = sorted_stats[:_MAX_DISPLAYED_FILE_STATS]
        stat_lines = [f"- {s.path}  (+{s.additions} / -{s.deletions})" for s in displayed]
        if len(sorted_stats) > _MAX_DISPLAYED_FILE_STATS:
            stat_lines.append(f"- ... (+{len(sorted_stats) - _MAX_DISPLAYED_FILE_STATS} more files)")
        stats_block = "\n".join(stat_lines) if stat_lines else "(no files)"

        # Story 3.5 code-review patch (P8): the PR title is attacker-
        # controlled (any GitHub user opening a PR against a watched
        # repo). Strip newlines + cap length before interpolation so a
        # crafted title cannot break the prompt structure or smuggle
        # instructions that override the role-adaptive Socratic
        # anti-cheat clauses. BYOK zero-retention limits blast radius
        # but hardening the external-input surface is essentially
        # free.
        safe_title = _sanitize_pr_title(pr_metadata.pr_title)

        return (
            f"Role: {pr_metadata.role.value}\n"
            f"PR title: {safe_title}\n"
            f"Changed files: {pr_metadata.changed_file_count}\n"
            f"Total lines changed: {pr_metadata.total_lines_changed}\n\n"
            f"Per-file line stats (largest-change first):\n{stats_block}\n\n"
            f"PR diff (possibly truncated for large PRs — see above stats for the full picture):\n"
            f"{pr_diff}\n\n"
            f"Previous questions you already asked (do not repeat):\n"
            f"{previous_block}\n\n"
            "Ask the next Socratic question. Remember: probe beyond the "
            "diff when the change warrants it."
        )

    async def generate_score(
        self,
        *,
        session_id: UUID,
        session_role: SessionRole,
        pr_title: str,
        questions_and_answers: list[tuple[str, str, str]],
        pr_metadata: PRPromptContext,
        api_key: str,
    ) -> Score:
        """Evaluate the complete Q&A session and return a ``Score``.

        Non-streaming structured output via ``output_type=ScoringResult``.
        The LLM produces four dimension scores + gap bullets; Python
        derives the ``Verdict`` deterministically.
        """
        from helprs.modules.comprehension.domain.entities import Score as ScoreEntity

        agent = self._build_score_agent(api_key, role=session_role)
        prompt = self._render_score_prompt(
            pr_title=pr_title,
            pr_metadata=pr_metadata,
            questions_and_answers=questions_and_answers,
        )
        result = await agent.run(prompt)
        scoring: ScoringResult = result.output

        verdict = derive_verdict(scoring.depth, scoring.accuracy, scoring.completeness, scoring.insight)

        return ScoreEntity(
            session_id=session_id,
            depth=scoring.depth,
            accuracy=scoring.accuracy,
            completeness=scoring.completeness,
            insight=scoring.insight,
            verdict=verdict,
            gap_summary=tuple(scoring.gaps),
            created_at=datetime.now(UTC),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_feedback_agent(self, api_key: str) -> Agent:
        """Construct a fresh feedback ``Agent`` with the per-call key.

        Distinct seam from ``_build_agent`` (the question agent) so
        unit tests can monkeypatch the feedback path independently.
        Same zero-retention rule: fresh ``Agent`` per call, never
        cached on the instance.
        """
        model = AnthropicModel(
            _ANTHROPIC_MODEL_ID,
            provider=AnthropicProvider(api_key=api_key),
        )
        return Agent(model, system_prompt=FEEDBACK_SYSTEM_PROMPT)

    def _render_feedback_prompt(
        self,
        *,
        question_text: str,
        answer_text: str,
        pr_diff: str,
        role: SessionRole,
    ) -> str:
        """Render the per-call feedback user prompt.

        Story 3.4 scaffold — kept verbatim in Story 3.5. Feedback
        role-adaptation is owned by Epic 4 (scoring).
        """
        return (
            f"Role: {role.value}\n\n"
            f"PR diff:\n{pr_diff}\n\n"
            f"The question you asked was:\n{question_text}\n\n"
            f"The developer answered:\n{answer_text}\n\n"
            "Give your feedback now."
        )

    def _build_score_agent(self, api_key: str, *, role: SessionRole) -> Agent:
        """Construct a fresh scoring ``Agent`` with structured output.

        Story 4.1: uses ``output_type=ScoringResult`` so Pydantic AI
        forces the LLM to return valid JSON matching the schema.
        Role-adaptive system prompt picks AUTHOR vs REVIEWER scoring
        criteria. Same zero-retention rule: fresh Agent per call.
        """
        model = AnthropicModel(
            _ANTHROPIC_MODEL_ID,
            provider=AnthropicProvider(api_key=api_key),
        )
        if role is SessionRole.AUTHOR:
            system = AUTHOR_SCORING_SYSTEM_PROMPT
        elif role is SessionRole.REVIEWER:
            system = REVIEWER_SCORING_SYSTEM_PROMPT
        else:
            raise ValueError(f"_build_score_agent received unhandled SessionRole: {role!r}")
        return Agent(model, system_prompt=system, output_type=ScoringResult)

    def _render_score_prompt(
        self,
        *,
        pr_title: str,
        pr_metadata: PRPromptContext,
        questions_and_answers: list[tuple[str, str, str]],
    ) -> str:
        """Render the scoring prompt with the complete Q&A history."""
        safe_title = _sanitize_pr_title(pr_title)

        qa_block_parts: list[str] = []
        for i, (q, a, f) in enumerate(questions_and_answers, 1):
            qa_block_parts.append(f"--- Question {i} ---\nQ: {q}\nA: {a}\nFeedback given: {f}")
        qa_block = "\n\n".join(qa_block_parts) if qa_block_parts else "(no Q&A pairs)"

        return (
            f"PR title: {safe_title}\n"
            f"Changed files: {pr_metadata.changed_file_count}\n"
            f"Total lines changed: {pr_metadata.total_lines_changed}\n\n"
            f"Complete Q&A session ({len(questions_and_answers)} questions):\n\n"
            f"{qa_block}\n\n"
            "Now evaluate the developer's overall comprehension across the four dimensions "
            "and identify 2-4 specific areas to deepen."
        )
