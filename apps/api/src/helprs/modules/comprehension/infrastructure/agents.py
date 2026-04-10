"""Concrete ``LLMProvider`` implementations.

Story 3.1 shipped the ``NullLLMProvider`` stub.
Story 3.3 introduces ``PydanticAILLMProvider`` — the production
provider backed by Pydantic AI 1.78 + Anthropic Claude Sonnet 4.5.

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
* **Minimal prompt scaffold.** Story 3.3 ships a minimal role-aware
  prompt; Story 3.5 replaces it with the full challenge-me SKILL.md
  adaptation (role-adaptive, tradeoff probing, architectural
  reasoning). A ``TODO(story-3.5)`` marker at the prompt location
  makes the seam obvious.

Pydantic AI 1.78 streaming API reference (Context7):
https://github.com/pydantic/pydantic-ai/blob/v1.71.0/docs/output.md
- ``async with agent.run_stream(prompt) as result:``
- ``async for chunk in result.stream_text(delta=True):``

Anthropic provider with explicit API key (Context7):
https://github.com/pydantic/pydantic-ai/blob/v1.71.0/docs/models/anthropic.md
- ``AnthropicModel('claude-sonnet-4-5',
    provider=AnthropicProvider(api_key=...))``
"""

from collections.abc import AsyncIterator

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from helprs.modules.comprehension.domain.value_objects import SessionRole

# Model ID — the story pins ``claude-sonnet-4-5``. If Anthropic ships a
# newer stable before we flip to Story 3.5's full prompt, bump here (and
# only here).
_ANTHROPIC_MODEL_ID = "claude-sonnet-4-5"

# TODO(story-3.5): replace this minimal scaffold with the role-adaptive
# challenge-me SKILL.md adaptation (~220 lines, author/reviewer
# branching, tradeoff probing, architectural reasoning).
QUESTION_SYSTEM_PROMPT = """You are a Socratic code reviewer helping a developer \
think deeply about their pull request. Ask one focused question at a time.
The question should:
- Reveal a gap in understanding or an assumption the developer may not have examined
- Reference specific file paths or code sections from the diff when possible
- Probe decisions, tradeoffs, or edge cases — not trivia
- Be conversational in tone, ~1-3 sentences
- End with a question mark

Do not answer the question. Do not provide hints. Do not critique; just ask."""


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
        role: SessionRole,
        previous_questions: list[str],
        api_key: str,
    ) -> AsyncIterator[str]:
        raise NotImplementedError("LLMProvider is wired in Story 3.3")

    async def generate_question(
        self,
        *,
        pr_diff: str,
        role: SessionRole,
        previous_questions: list[str],
        api_key: str,
    ) -> str:
        raise NotImplementedError("LLMProvider is wired in Story 3.3")

    async def generate_feedback(
        self,
        *,
        question: str,
        answer: str,
        pr_diff: str,
        api_key: str,
    ) -> str:
        raise NotImplementedError("LLMProvider is wired in Story 3.3")


class PydanticAILLMProvider:
    """Production ``LLMProvider`` backed by Pydantic AI + Anthropic.

    Zero-retention by construction: the ``Agent`` is built per call
    with the user's decrypted BYOK key. Neither the key nor the
    ``pr_diff`` is persisted here — both flow through as arguments.

    ``generate_feedback`` is deferred to Story 3.4.
    """

    async def stream_question(
        self,
        *,
        pr_diff: str,
        role: SessionRole,
        previous_questions: list[str],
        api_key: str,
    ) -> AsyncIterator[str]:
        """Yield text deltas as Claude produces the next question.

        Each yielded value is a partial chunk (``delta=True``). The
        caller accumulates these into the full question text before
        hashing it for persistence.
        """
        agent = self._build_agent(api_key)
        prompt = self._render_prompt(
            pr_diff=pr_diff,
            role=role,
            previous_questions=previous_questions,
        )
        async with agent.run_stream(prompt) as result:
            async for chunk in result.stream_text(delta=True):
                yield chunk

    async def generate_question(
        self,
        *,
        pr_diff: str,
        role: SessionRole,
        previous_questions: list[str],
        api_key: str,
    ) -> str:
        """Non-streaming convenience — consume ``stream_question`` fully."""
        parts: list[str] = []
        async for chunk in self.stream_question(
            pr_diff=pr_diff,
            role=role,
            previous_questions=previous_questions,
            api_key=api_key,
        ):
            parts.append(chunk)
        return "".join(parts)

    async def generate_feedback(
        self,
        *,
        question: str,
        answer: str,
        pr_diff: str,
        api_key: str,
    ) -> str:
        raise NotImplementedError("Feedback generation is Story 3.4")

    # ------------------------------------------------------------------
    # Internals — kept narrow so tests can monkeypatch ``_build_agent``
    # ------------------------------------------------------------------

    def _build_agent(self, api_key: str) -> Agent:
        """Construct a fresh ``Agent`` with a per-call Anthropic provider.

        Split out as a seam for unit tests: they can ``monkeypatch``
        this method to return a fake ``Agent`` backed by a scripted
        ``run_stream`` context manager, avoiding any real Anthropic
        traffic.
        """
        model = AnthropicModel(
            _ANTHROPIC_MODEL_ID,
            provider=AnthropicProvider(api_key=api_key),
        )
        return Agent(model, system_prompt=QUESTION_SYSTEM_PROMPT)

    def _render_prompt(
        self,
        *,
        pr_diff: str,
        role: SessionRole,
        previous_questions: list[str],
    ) -> str:
        """Render the per-call user prompt from the session context.

        Story 3.3 uses a role-aware-but-minimal template; Story 3.5
        swaps it for the full role-adapted version.
        """
        previous_block = (
            "\n".join(f"- {q}" for q in previous_questions)
            if previous_questions
            else "(none yet — this is the first question)"
        )
        return (
            f"Role: {role.value}\n"
            f"PR diff:\n{pr_diff}\n\n"
            f"Previous questions you already asked (do not repeat):\n"
            f"{previous_block}\n\n"
            "Ask the next Socratic question."
        )
