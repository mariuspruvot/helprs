"""Comprehension repository implementations.

``SqlAlchemySessionRepository`` is the concrete implementation of the
domain ``SessionRepository`` protocol. It owns the ORM ↔ domain mapping
for ``SessionModel`` ↔ ``Session``.

Unit-of-work rule: this repository never calls ``session.commit()``. The
outer handler (``StartSessionHandler``) and, above that,
``process_webhook_event`` own the transaction boundary so exceptions roll
back cleanly. This is deliberately the opposite of the webhook repository
(which commits eagerly to survive crashes).
"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.exceptions import DomainValidationError
from helprs.modules.comprehension.domain.entities import Answer, PRContext, Question, Score, Session
from helprs.modules.comprehension.domain.value_objects import SessionRole, SessionStatus, Topic, Verdict
from helprs.modules.comprehension.infrastructure.models import AnswerModel, QuestionModel, ScoreModel, SessionModel


def _to_domain(row: SessionModel) -> Session:
    """Map an ORM row to a domain ``Session``.

    Kept private to this module — mapping is infrastructure plumbing and
    must not leak into ``domain/entities.py``.
    """
    return Session(
        id=row.id,
        installation_id=row.installation_id,
        github_installation_id=row.github_installation_id,
        repo_full_name=row.repo_full_name,
        repo_owner=row.repo_owner,
        repo_name=row.repo_name,
        pr_number=row.pr_number,
        pr_title=row.pr_title,
        pr_head_sha=row.pr_head_sha,
        pr_diff_url=row.pr_diff_url,
        role=SessionRole(row.role),
        status=SessionStatus(row.status),
        total_questions=row.total_questions,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_domain_question(row: QuestionModel) -> Question:
    """Map an ORM ``QuestionModel`` row to a domain ``Question``.

    Mirrors ``_to_domain`` for sessions. The verbatim question text is
    intentionally absent from both the ORM row and the domain entity
    (FR35/NFR14) — only the SHA-256 ``text_hash`` is persisted.
    """
    return Question(
        id=row.id,
        session_id=row.session_id,
        number=row.number,
        topic=Topic(row.topic),
        text_hash=row.text_hash,
        created_at=row.created_at,
    )


def _to_domain_answer(row: AnswerModel) -> Answer:
    """Map an ORM ``AnswerModel`` row to a domain ``Answer``.

    Story 3.4: mirror of ``_to_domain_question``. Same hash-only
    privacy rule — the verbatim answer text never lives in either the
    ORM row or the domain entity (FR35/NFR14).
    """
    return Answer(
        id=row.id,
        question_id=row.question_id,
        text_hash=row.text_hash,
        latency_ms=row.latency_ms,
        created_at=row.created_at,
    )


def _to_domain_score(row: ScoreModel) -> Score:
    """Map an ORM ``ScoreModel`` row to a domain ``Score``."""
    return Score(
        session_id=row.session_id,
        depth=row.depth,
        accuracy=row.accuracy,
        completeness=row.completeness,
        insight=row.insight,
        verdict=Verdict(row.verdict),
        gap_summary=tuple(row.gap_summary),
        created_at=row.created_at,
    )


class SqlAlchemySessionRepository:
    """Concrete ``SessionRepository`` backed by an AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_pair(
        self,
        *,
        pr_ctx: PRContext,
        total_questions: int = 5,
    ) -> tuple[Session, Session]:
        """Insert an (author, reviewer) pair and flush to assign IDs.

        Story 3.3: ``total_questions`` is now written onto both rows at
        creation time using ``StartSessionHandler``'s line-count
        heuristic. Defaults to ``5`` for backward compatibility with
        tests that don't care about sizing.
        """
        shared = pr_ctx.to_columns()
        author = SessionModel(
            role=SessionRole.AUTHOR.value,
            status=SessionStatus.PENDING.value,
            total_questions=total_questions,
            **shared,
        )
        reviewer = SessionModel(
            role=SessionRole.REVIEWER.value,
            status=SessionStatus.PENDING.value,
            total_questions=total_questions,
            **shared,
        )
        self._session.add_all((author, reviewer))
        # Flush — not commit — so the caller retains unit-of-work control.
        # IDs + created_at/updated_at are populated here.
        await self._session.flush()
        await self._session.refresh(author)
        await self._session.refresh(reviewer)
        return _to_domain(author), _to_domain(reviewer)

    async def find_pair(
        self,
        *,
        installation_id: UUID,
        repo_full_name: str,
        pr_number: int,
    ) -> list[Session]:
        """Return 0, 1 (corrupted), or 2 rows for the PR."""
        result = await self._session.execute(
            select(SessionModel)
            .where(
                SessionModel.installation_id == installation_id,
                SessionModel.repo_full_name == repo_full_name,
                SessionModel.pr_number == pr_number,
            )
            .order_by(SessionModel.role)
        )
        rows = list(result.scalars().all())
        return [_to_domain(r) for r in rows]

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

        Uses a single ``update(...).where(...)`` — no per-row roundtrip.
        The subsequent ``SELECT`` returns the refreshed domain entities so
        callers can log / inspect them.
        """
        stmt = (
            update(SessionModel)
            .where(
                SessionModel.installation_id == installation_id,
                SessionModel.repo_full_name == repo_full_name,
                SessionModel.pr_number == pr_number,
            )
            .values(
                pr_head_sha=new_head_sha,
                pr_title=new_pr_title,
                pr_diff_url=new_pr_diff_url,
            )
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(stmt)
        await self._session.flush()
        # Re-fetch: the UPDATE statement doesn't populate Python-side objects
        # and ``updated_at`` is refreshed server-side by the ``onupdate`` hook.
        return await self.find_pair(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
        )

    async def delete_one(self, *, session_id: UUID) -> None:
        """Delete a single session row by id.

        Used by the handler's orphan-recovery path (1-row case in
        ``find_pair``). Intentionally narrow — no bulk/delete-by-PR surface
        area; Story 3.1 will decide the lifecycle story for delete.
        """
        row = await self._session.get(SessionModel, session_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def get_by_id(self, *, session_id: UUID) -> Session | None:
        """Load a single session by primary key.

        Uses ``AsyncSession.get`` so SQLAlchemy's identity map handles
        caching within the unit of work. Returns ``None`` for unknown
        ids. Read-only — does not commit (locked by a dedicated test).
        """
        row = await self._session.get(SessionModel, session_id)
        return _to_domain(row) if row is not None else None

    # ------------------------------------------------------------------
    # Story 3.3: question persistence
    # ------------------------------------------------------------------

    async def count_questions(self, *, session_id: UUID) -> int:
        """Return the number of ``QuestionModel`` rows for the session."""
        result = await self._session.execute(
            select(func.count()).select_from(QuestionModel).where(QuestionModel.session_id == session_id)
        )
        return int(result.scalar_one())

    async def list_questions(self, *, session_id: UUID) -> list[Question]:
        """Return all questions for the session, ordered by ``number`` ASC."""
        result = await self._session.execute(
            select(QuestionModel).where(QuestionModel.session_id == session_id).order_by(QuestionModel.number.asc())
        )
        rows = list(result.scalars().all())
        return [_to_domain_question(r) for r in rows]

    async def append_question(
        self,
        *,
        session_id: UUID,
        topic: Topic,
        text_hash: str,
    ) -> Question:
        """Insert a new question row, auto-incrementing ``number``.

        Serializes concurrent inserts for the same session with a
        ``SELECT ... FOR UPDATE`` row lock on the parent ``sessions``
        row, then computes ``next_number = max(number) + 1`` inside
        the lock. This is simpler than a sequence per session and
        keeps the ``(session_id, number)`` invariant sound under
        concurrent SSE streams (e.g. user opens two tabs).

        UoW rule: flushes but does NOT commit — the caller's outer
        ``async with get_db_context() as tx`` block commits on
        successful exit.
        """
        # Row-level lock on the parent session. asyncpg translates this
        # to ``SELECT ... FOR UPDATE`` at the wire level.
        await self._session.execute(select(SessionModel.id).where(SessionModel.id == session_id).with_for_update())
        # Compute the next number while holding the lock. ``COALESCE``
        # because the first question on a session has ``MAX == NULL``.
        max_result = await self._session.execute(
            select(func.coalesce(func.max(QuestionModel.number), 0)).where(QuestionModel.session_id == session_id)
        )
        next_number = int(max_result.scalar_one()) + 1

        row = QuestionModel(
            session_id=session_id,
            number=next_number,
            topic=topic.value,
            text_hash=text_hash,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain_question(row)

    # ------------------------------------------------------------------
    # Story 3.4: answer persistence
    # ------------------------------------------------------------------

    async def get_question_by_number(
        self,
        *,
        session_id: UUID,
        number: int,
    ) -> Question | None:
        """Single-row lookup of a question by its 1-indexed ``number``.

        Returns ``None`` for unknown numbers; the POST handler maps
        that to 404. Read-only — does not commit.
        """
        result = await self._session.execute(
            select(QuestionModel)
            .where(
                QuestionModel.session_id == session_id,
                QuestionModel.number == number,
            )
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_domain_question(row) if row is not None else None

    async def count_answers(self, *, session_id: UUID) -> int:
        """Count answers persisted across the session's questions.

        Joined query so the SSE GET stream can compute "the next
        un-answered question number" without holding a stale snapshot
        of the questions table.
        """
        result = await self._session.execute(
            select(func.count())
            .select_from(AnswerModel)
            .join(QuestionModel, AnswerModel.question_id == QuestionModel.id)
            .where(QuestionModel.session_id == session_id)
        )
        return int(result.scalar_one())

    async def append_answer(
        self,
        *,
        question_id: UUID,
        text_hash: str,
        latency_ms: int,
    ) -> Answer:
        """Insert a new answer row.

        The DB-level ``UniqueConstraint('question_id')`` enforces
        "exactly one answer per question". On collision the
        ``IntegrityError`` is translated to ``DomainValidationError``
        so the POST handler can map it to 409 with a clean error
        code.

        Story 3.4 P3 (code-review): the insert is wrapped in an
        explicit savepoint (``begin_nested``) so a duplicate collision
        only rolls back the failed insert — NOT the surrounding
        request-scoped transaction (which may contain earlier reads
        or writes the caller still needs).
        """
        savepoint = await self._session.begin_nested()
        try:
            row = AnswerModel(
                question_id=question_id,
                text_hash=text_hash,
                latency_ms=latency_ms,
            )
            self._session.add(row)
            await self._session.flush()
        except IntegrityError as exc:
            await savepoint.rollback()
            raise DomainValidationError("answer already submitted for question") from exc
        else:
            await savepoint.commit()
        await self._session.refresh(row)
        return _to_domain_answer(row)

    # ------------------------------------------------------------------
    # Story 4.1: score persistence
    # ------------------------------------------------------------------

    async def persist_score(self, *, score: Score) -> None:
        """Insert a score row for the session.

        One score per session — the unique constraint on ``session_id``
        prevents duplicates. Uses a savepoint so a duplicate on SSE
        reconnect raises ``DomainValidationError`` instead of crashing.
        Flushes but does NOT commit.
        """
        row = ScoreModel(
            session_id=score.session_id,
            depth=score.depth,
            accuracy=score.accuracy,
            completeness=score.completeness,
            insight=score.insight,
            verdict=score.verdict.value,
            gap_summary=list(score.gap_summary),
        )
        self._session.add(row)
        savepoint = await self._session.begin_nested()
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await savepoint.rollback()
            raise DomainValidationError("score already exists for session") from exc
        else:
            await savepoint.commit()

    async def get_score_by_session_id(self, *, session_id: UUID) -> Score | None:
        """Load the score for a session, or ``None`` if not yet scored."""
        result = await self._session.execute(select(ScoreModel).where(ScoreModel.session_id == session_id).limit(1))
        row = result.scalar_one_or_none()
        return _to_domain_score(row) if row is not None else None
