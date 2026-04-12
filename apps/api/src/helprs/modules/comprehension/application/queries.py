"""Comprehension application queries.

Story 3.1 adds ``GetSessionQuery`` and ``GetSessionResult`` for the
``GET /api/v1/sessions/{id}`` read path. The handler sits in
``handlers.py`` so it is colocated with ``StartSessionHandler`` for
consistency with existing CQRS patterns in the module.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from helprs.modules.comprehension.domain.entities import Score, Session

if TYPE_CHECKING:
    from helprs.modules.identity.models import GitHubUser


@dataclass(frozen=True, slots=True)
class QuestionProgressEntry:
    """Per-question resume entry — `(number, status, topic)`.

    Story 3.4: returned in ``GetSessionResult.progress`` so the router
    can map it through to the response. Plain dataclass (not Pydantic)
    so the application layer stays free of presentation imports.
    """

    number: int
    status: Literal["answered", "in_flight"]
    topic: str


@dataclass(frozen=True, slots=True)
class GetSessionQuery:
    """Inputs for the session detail read path.

    ``requesting_user`` is the ``GitHubUser`` row already loaded by the
    FastAPI ``get_current_user`` dependency. Passing the full object
    avoids a second ``SELECT`` inside the handler (the router and the
    handler share the same ``AsyncSession``, so the row is already in
    the identity map anyway).
    """

    session_id: UUID
    requesting_user: "GitHubUser"


@dataclass(frozen=True, slots=True)
class GetSessionResult:
    """Outputs of ``GetSessionHandler.handle``.

    The handler intentionally does NOT fetch the diff itself — it stays
    inside the DB scope. The router (outside the DB scope) uses
    ``installation_token`` + the session's repo metadata to fetch the
    diff via ``fetch_pr_diff``. This split is the pattern precedent
    Epic 2's retrospective flagged as a blocker for Story 3.3.

    ``question_count`` is hardcoded to 0 for Story 3.1; Story 3.3
    populates it once ``QuestionModel`` exists.

    ``installation_token`` is a short-lived (~1 h) GitHub App scoped
    token. ``__repr__`` is overridden to mask it so structured logging
    helpers (structlog, Sentry) cannot accidentally serialize the
    secret when they capture a result for context.
    """

    session: Session
    installation_token: str
    question_count: int
    # Story 3.4: per-question progress for the resume-from-reload UX.
    # Tuple keeps the dataclass frozen-friendly. Empty for sessions
    # whose question stream has not started yet.
    progress: tuple[QuestionProgressEntry, ...] = field(default_factory=tuple)
    # Story 4.1: score breakdown — None for unscored sessions.
    score: "Score | None" = None

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return (
            f"GetSessionResult(session={self.session!r}, "
            f"installation_token='<redacted>', "
            f"question_count={self.question_count}, "
            f"progress=<{len(self.progress)} entries>)"
        )
