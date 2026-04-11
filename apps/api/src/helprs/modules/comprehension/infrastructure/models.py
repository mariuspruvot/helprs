"""Comprehension SQLAlchemy ORM models.

``SessionModel`` is deliberately named with the ``Model`` suffix so it does
not shadow SQLAlchemy's ``Session`` / the domain ``Session`` entity. The
domain ↔ ORM mapping lives in ``repositories.py``.

Story 3.3 adds ``QuestionModel`` — the metadata-only persistence layer for
Socratic questions. **There is no ``text`` column**: FR35/NFR14 forbid
storing verbatim question text on disk. Only a SHA-256 ``text_hash`` is
persisted. If you are tempted to add ``text`` for debugging, log to
structlog at ``debug`` level (gated by env) instead.
"""

import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from helprs.core.database import Base


class SessionModel(Base):
    """A single comprehension session — one side (author or reviewer) of a PR.

    Session pairs are keyed on ``(installation_id, repo_full_name, pr_number,
    role)``; the unique constraint enforces that exactly one row per role
    exists per PR. Story 3.1 will extend this model with question/answer
    links.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint(
            "installation_id",
            "repo_full_name",
            "pr_number",
            "role",
            name="uq_sessions_installation_pr_role",
        ),
    )

    installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installations.id"),
        index=True,
        nullable=False,
    )
    github_installation_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )
    repo_full_name: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    repo_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_title: Mapped[str] = mapped_column(String(1024), nullable=False)
    pr_head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    pr_diff_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # Story 3.3: count of questions the session plans to ask (set once at
    # session creation time by ``StartSessionHandler`` using
    # ``estimate_question_count``). The migration uses a transient
    # ``server_default='0'`` to backfill existing rows, then drops it
    # so the application layer is the only source of truth. The
    # Python-side ``default=0`` is kept as a belt-and-braces fallback
    # for tests that build sessions without specifying a value.
    total_questions: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )


class QuestionModel(Base):
    """A single Socratic question asked during a comprehension session.

    **No ``text`` column — only ``text_hash``.** FR35/NFR14 forbid
    persisting verbatim question text. The raw text is regenerated on
    demand by the LLM port and never touches disk.

    The ``(session_id, number)`` unique constraint is the ordering
    invariant: questions are numbered ``1..N`` per session, and
    ``SqlAlchemySessionRepository.append_question`` uses a
    ``SELECT ... FOR UPDATE`` lock on the sessions row to make the
    per-session number assignment atomic under concurrent streams.

    Note: no separate single-column index on ``session_id`` — the unique
    constraint above already builds a B-tree whose leftmost column is
    ``session_id``, which covers both ``WHERE session_id = ?`` lookups
    and the ``ORDER BY number`` scan used by ``list_questions``.
    """

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "number",
            name="uq_questions_session_number",
        ),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    topic: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 hex digest (64 chars). Hash-only storage is the core
    # privacy promise of helPRs — do NOT add a ``text`` column alongside
    # this, even "temporarily".
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AnswerModel(Base):
    """A developer's answer to a ``QuestionModel``.

    Story 3.4: metadata-only persistence layer for answers, mirror of
    ``QuestionModel``. **There is no ``text`` column** — FR35/NFR14
    forbid persisting verbatim answer text. Only the SHA-256
    ``text_hash`` is persisted alongside the ``latency_ms`` observability
    hook (Epic 4 scoring).

    The ``UniqueConstraint`` on ``question_id`` enforces "exactly one
    answer per question" at the DB level — concurrent double-submits
    surface as ``IntegrityError`` which the repository translates to
    ``DomainValidationError`` so the POST endpoint can map it to 409.
    No separate single-column index on ``question_id`` is needed: the
    unique constraint already builds a B-tree on that column (mirror of
    Story 3-3's ``questions`` table decision).
    """

    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint(
            "question_id",
            name="uq_answers_question_id",
        ),
    )

    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SHA-256 hex digest (64 chars). Same hash-only privacy rule as
    # ``QuestionModel`` — do NOT add a ``text`` column.
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Wall-clock milliseconds between question commit (``Question.created_at``)
    # and answer POST receipt. Observability hook for Epic 4 scoring;
    # Story 3.4 itself does not consume the value. ``BigInteger`` rather
    # than ``Integer`` so a tab left open for ≥25 days (Integer overflow
    # at 2**31-1 ms ≈ 24.85 d) does not 500 the POST.
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
