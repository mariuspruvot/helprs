"""Comprehension domain interfaces (ports).

Story 2.2 introduced the ``SessionRepository`` port used by the
``StartSessionHandler`` to persist session pairs. Story 3.1 extends the
repository contract with ``get_by_id`` (for the GET endpoint) and adds
the ``LLMProvider`` port — the contract Story 3.3's PydanticAI provider
will implement. Story 3.5 tightens the ``stream_question`` /
``generate_question`` signatures to take a ``PRPromptContext`` instead
of a bare ``SessionRole``.

Domain purity note (Story 3.5): ``PRPromptContext`` lives in
``infrastructure/`` because it is a prompt-assembly DTO, not a domain
concept. The Protocol references it via a ``TYPE_CHECKING`` import so
the domain package never imports infrastructure at runtime. The
``test_domain_purity`` AST walker only forbids ``sqlalchemy``,
``fastapi``, ``httpx``, and ``pydantic_ai`` — ``helprs.*`` relative
imports are permitted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from helprs.modules.comprehension.domain.entities import Answer, PRContext, Question, Score, Session
    from helprs.modules.comprehension.domain.value_objects import SessionRole, Topic
    from helprs.modules.comprehension.infrastructure.agents import PRPromptContext


class SessionRepository(Protocol):
    """Port for persisting/loading session pairs.

    Implemented by ``SqlAlchemySessionRepository`` in the infrastructure
    layer. Story 2.2's three methods stay untouched; Story 3.1 adds
    ``get_by_id`` for the detail endpoint.
    """

    async def add_pair(self, *, pr_ctx: PRContext) -> tuple[Session, Session]:
        """Insert an (author, reviewer) session pair for the PR.

        Returns the two domain entities with populated IDs. The underlying
        ORM session is flushed (to assign IDs) but NOT committed — the
        caller owns the unit of work.
        """
        ...

    async def update_head_sha(
        self,
        *,
        installation_id: UUID,
        repo_full_name: str,
        pr_number: int,
        new_head_sha: str,
        new_pr_title: str,
        new_pr_diff_url: str,
    ) -> list[Session]:
        """Update PR-head metadata on both rows of an existing pair.

        Returns the refreshed domain entities. Used on
        ``pull_request.synchronize`` to keep the session pointed at the
        latest commit without re-posting the PR comment.
        """
        ...

    async def find_pair(
        self,
        *,
        installation_id: UUID,
        repo_full_name: str,
        pr_number: int,
    ) -> list[Session]:
        """Look up the session pair for a given PR.

        Returns 0, 1 (corrupted — caller should recover), or 2 rows. The
        caller decides whether to create, recover, or update.
        """
        ...

    async def get_by_id(self, *, session_id: UUID) -> Session | None:
        """Load a single session by primary key.

        Returns ``None`` when the row is absent. Used by the detail
        endpoint and the forthcoming question/answer submission paths.
        """
        ...

    # ------------------------------------------------------------------
    # Story 3.3: question persistence (metadata-only — hash, never text)
    # ------------------------------------------------------------------

    async def count_questions(self, *, session_id: UUID) -> int:
        """Return the number of questions already persisted for the session.

        Used by ``GetSessionHandler`` to populate ``question_count`` on
        the detail response, replacing the Story 3.1 hardcoded ``0``.
        """
        ...

    async def list_questions(self, *, session_id: UUID) -> list[Question]:
        """List all persisted questions for a session, ordered by ``number``.

        Used by the SSE endpoint to decide which question numbers still
        need to be generated (supports resume-after-disconnect without
        duplicating already-persisted questions).
        """
        ...

    async def append_question(
        self,
        *,
        session_id: UUID,
        topic: Topic,
        text_hash: str,
    ) -> Question:
        """Persist a new question for the session, auto-incrementing ``number``.

        The implementation takes a ``SELECT ... FOR UPDATE`` row lock on
        the sessions row so the ``(session_id, number)`` uniqueness
        invariant holds under concurrent streams. Flushes but does NOT
        commit — the caller (an outer ``get_db_context`` block) owns
        the transaction boundary.
        """
        ...

    # ------------------------------------------------------------------
    # Story 3.4: answer persistence (metadata-only — hash, never text)
    # ------------------------------------------------------------------

    async def get_question_by_number(
        self,
        *,
        session_id: UUID,
        number: int,
    ) -> Question | None:
        """Single-row lookup of a question by its 1-indexed ``number``.

        Used by the answer-submission POST handler to resolve a
        ``(session_id, number)`` pair from the URL/body to the actual
        ``question_id`` it must persist the answer against. Returns
        ``None`` for unknown numbers; the handler maps that to 404.
        """
        ...

    async def count_answers(self, *, session_id: UUID) -> int:
        """Return the number of answers persisted across the session's questions.

        Used by the SSE GET stream to compute "the next un-answered
        question number" on resume — closing the deferred bug from
        Story 3-3 manual QA where reopening a session whose questions
        were all persisted-but-unanswered would emit ``done`` instead
        of advancing the loop.
        """
        ...

    async def append_answer(
        self,
        *,
        question_id: UUID,
        text_hash: str,
        latency_ms: int,
    ) -> Answer:
        """Persist a new answer for the given question.

        The DB-level ``UniqueConstraint('question_id')`` enforces
        "exactly one answer per question". On collision the
        implementation translates the ``IntegrityError`` to
        ``DomainValidationError`` so the POST handler can map it to
        409. Flushes but does NOT commit ��� the caller (the request-
        scoped ``db`` for the POST handler's DB phase) owns the
        transaction boundary.
        """
        ...

    # ------------------------------------------------------------------
    # Story 4.1: score persistence (metadata-only)
    # ------------------------------------------------------------------

    async def persist_score(self, *, score: Score) -> None:
        """Insert the session's score row.

        One score per session (unique constraint on ``session_id``).
        Flushes but does NOT commit — the caller owns the transaction.
        """
        ...

    async def get_score_by_session_id(self, *, session_id: UUID) -> Score | None:
        """Load the score for a session, or ``None`` if not yet scored."""
        ...


class LLMProvider(Protocol):
    """Port for LLM calls.

    Story 3.1 only declares the contract so application-layer code can
    depend on a stable shape; the concrete ``PydanticAILLMProvider``
    ships in Story 3.3. The call sites pass the in-memory PR diff and
    the user's decrypted BYOK key as plain strings — neither is
    persisted anywhere along this path (FR35/NFR13).
    """

    def stream_question(
        self,
        *,
        pr_diff: str,
        pr_metadata: PRPromptContext,
        previous_questions: list[str],
        api_key: str,
    ) -> AsyncIterator[str]:
        """Yield question-text chunks as they arrive from the LLM.

        Story 3.5: ``pr_metadata`` carries role, PR title, line stats,
        and per-file stats. The fresh-Agent-per-call rule means
        ``api_key`` is passed as a function argument and never stashed on
        the provider instance (zero-retention, FR34).
        """
        ...

    async def generate_question(
        self,
        *,
        pr_diff: str,
        pr_metadata: PRPromptContext,
        previous_questions: list[str],
        api_key: str,
    ) -> str:
        """Non-streaming convenience: consume ``stream_question`` fully
        and return the concatenated text. Kept so legacy callers and
        tests that do not care about streaming semantics continue to
        work unchanged.
        """
        ...

    def stream_feedback(
        self,
        *,
        question_text: str,
        answer_text: str,
        pr_diff: str,
        role: SessionRole,
        api_key: str,
    ) -> AsyncIterator[str]:
        """Yield feedback text deltas as Claude evaluates the answer.

        Story 3.4 production path. Each yielded value is a partial
        chunk (``delta=True``). The caller accumulates these into the
        full feedback text before extracting code refs and emitting
        the authoritative ``event: feedback`` SSE frame. The
        fresh-Agent-per-call rule applies just like
        ``stream_question`` — ``api_key`` is a function argument and
        is never stashed on the provider instance (zero-retention,
        FR34).
        """
        ...

    async def generate_feedback(
        self,
        *,
        question_text: str,
        answer_text: str,
        pr_diff: str,
        role: SessionRole,
        api_key: str,
    ) -> str:
        """Non-streaming convenience: consume ``stream_feedback`` fully
        and return the concatenated text. Kept symmetric with
        ``generate_question``.
        """
        ...

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

        Story 4.1: non-streaming structured output. ``questions_and_answers``
        is a list of ``(question_text, answer_text, feedback_text)`` triples
        — ephemeral, never persisted. The LLM produces four dimension scores
        (0-10) + gap bullets; the caller derives the ``Verdict`` deterministically.

        Fresh Agent per call with BYOK key (zero-retention FR34).
        """
        ...
