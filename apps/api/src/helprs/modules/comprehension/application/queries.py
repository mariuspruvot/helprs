"""Comprehension application queries.

Story 3.1 adds ``GetSessionQuery`` and ``GetSessionResult`` for the
``GET /api/v1/sessions/{id}`` read path. The handler sits in
``handlers.py`` so it is colocated with ``StartSessionHandler`` for
consistency with existing CQRS patterns in the module.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from helprs.modules.comprehension.domain.entities import Session

if TYPE_CHECKING:
    from helprs.modules.identity.models import GitHubUser


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

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return (
            f"GetSessionResult(session={self.session!r}, "
            f"installation_token='<redacted>', "
            f"question_count={self.question_count})"
        )
