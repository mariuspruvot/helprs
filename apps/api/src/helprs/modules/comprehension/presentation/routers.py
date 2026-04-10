"""Comprehension API routers.

Story 3.1 exposes a single detail endpoint. The router is intentionally
thin: all business logic lives in ``GetSessionHandler``; the router
owns the DB-phase / HTTP-phase split so the GitHub diff fetch does not
run concurrently with any DB work the handler performed.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from helprs.core.dependencies import DbSession, GetSettings, get_current_user
from helprs.core.middleware import limiter
from helprs.modules.comprehension.application.handlers import GetSessionHandler
from helprs.modules.comprehension.application.queries import GetSessionQuery
from helprs.modules.comprehension.infrastructure.github_diff import fetch_pr_diff
from helprs.modules.comprehension.presentation.schemas import SessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionResponse)
@limiter.limit("60/minute")
async def get_session(
    session_id: UUID,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
) -> SessionResponse:
    """Return session metadata plus an in-memory unified diff.

    NFR13: the diff is fetched per request from GitHub and never
    persisted. FR26: the handler rejects callers whose GitHub identity
    lacks access to the session's installation with a 403.
    """
    # --- DB phase: load + authorize + mint token --------------------
    handler = GetSessionHandler(db, settings)
    result = await handler.handle(
        GetSessionQuery(
            session_id=session_id,
            requesting_user=user,
        )
    )
    # Snapshot everything before the HTTP phase so no ORM attribute
    # access can fire a lazy load while we're waiting on GitHub.
    session = result.session
    installation_token = result.installation_token
    question_count = result.question_count

    # --- HTTP phase: diff fetch runs AFTER the handler finishes -----
    # NOTE: FastAPI's get_db dependency still holds the AsyncSession
    # open until this function returns; the *structural* split here
    # sets the precedent Epic 2's retro flagged. Story 3.3 prep must
    # complete the fix before LLM calls (LLM latency >> diff latency).
    diff = await fetch_pr_diff(
        owner=session.repo_owner,
        repo=session.repo_name,
        pr_number=session.pr_number,
        installation_token=installation_token,
    )

    return SessionResponse(
        id=session.id,
        repo_full_name=session.repo_full_name,
        repo_owner=session.repo_owner,
        repo_name=session.repo_name,
        pr_number=session.pr_number,
        pr_title=session.pr_title,
        role=session.role,
        status=session.status,
        question_count=question_count,
        diff=diff,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )
