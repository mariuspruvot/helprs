"""Comprehension API routers.

Story 3.1 exposes a single detail endpoint. The router is intentionally
thin: all business logic lives in ``GetSessionHandler``; the router
owns the DB-phase / HTTP-phase split so the GitHub diff fetch does not
run concurrently with any DB work the handler performed.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from helprs.core.dependencies import DbSession, GetSettings, get_current_user
from helprs.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from helprs.core.middleware import limiter
from helprs.modules.comprehension.application.handlers import GetSessionHandler
from helprs.modules.comprehension.application.queries import GetSessionQuery
from helprs.modules.comprehension.domain.value_objects import SessionStatus
from helprs.modules.comprehension.infrastructure.github_diff import fetch_pr_diff
from helprs.modules.comprehension.infrastructure.repositories import SqlAlchemySessionRepository
from helprs.modules.comprehension.presentation.schemas import (
    QuestionProgress,
    QuestionReportRequest,
    QuestionReportResponse,
    ScoreResponse,
    SessionFeedbackRequest,
    SessionFeedbackResponse,
    SessionResponse,
)

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
    progress = [QuestionProgress(number=p.number, status=p.status, topic=p.topic) for p in result.progress]

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

    # Story 4.1: include score breakdown if available.
    score_response = None
    if result.score is not None:
        score_response = ScoreResponse(
            depth=result.score.depth,
            accuracy=result.score.accuracy,
            completeness=result.score.completeness,
            insight=result.score.insight,
            verdict=result.score.verdict.value,
            gaps=list(result.score.gap_summary),
        )

    # Story 4.2: include feedback if available.
    feedback_response = None
    if result.feedback is not None:
        feedback_response = SessionFeedbackResponse(
            rating=result.feedback.rating,
            comment=result.feedback.comment,
            created_at=result.feedback.created_at,
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
        total_questions=session.total_questions,
        diff=diff,
        created_at=session.created_at,
        updated_at=session.updated_at,
        progress=progress,
        score=score_response,
        feedback=feedback_response,
    )


@router.post(
    "/{session_id}/questions/{question_number}/report",
    response_model=QuestionReportResponse,
    status_code=201,
)
@limiter.limit("30/minute")
async def report_question(
    session_id: UUID,
    question_number: int,
    body: QuestionReportRequest,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
) -> QuestionReportResponse:
    """Flag a question as problematic (AC #2, #3).

    One report per question per session. Returns 409 if already reported.
    """
    handler = GetSessionHandler(db, settings)
    result = await handler.handle(GetSessionQuery(session_id=session_id, requesting_user=user))
    session = result.session

    # Validate question exists
    repo = SqlAlchemySessionRepository(db)
    question = await repo.get_question_by_number(session_id=session.id, number=question_number)
    if question is None:
        raise NotFoundError(f"Question {question_number} not found in session {session_id}")

    try:
        report = await repo.persist_question_report(
            session_id=session.id,
            question_number=question_number,
            reason=body.reason,
        )
    except DomainValidationError as exc:
        raise ConflictError(str(exc)) from exc

    return QuestionReportResponse(
        session_id=report.session_id,
        question_number=report.question_number,
        reason=report.reason,
        created_at=report.created_at,
    )


@router.post(
    "/{session_id}/feedback",
    response_model=SessionFeedbackResponse,
    status_code=201,
)
@limiter.limit("10/minute")
async def submit_feedback(
    session_id: UUID,
    body: SessionFeedbackRequest,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
) -> SessionFeedbackResponse:
    """Submit post-session feedback (AC #4, #5).

    Session must be COMPLETED. One feedback per session. Returns 409 if already submitted.
    """
    handler = GetSessionHandler(db, settings)
    result = await handler.handle(GetSessionQuery(session_id=session_id, requesting_user=user))
    session = result.session

    if session.status != SessionStatus.COMPLETED:
        raise DomainValidationError("Feedback can only be submitted for completed sessions")

    repo = SqlAlchemySessionRepository(db)
    try:
        feedback = await repo.persist_session_feedback(
            session_id=session.id,
            rating=body.rating,
            comment=body.comment,
        )
    except DomainValidationError as exc:
        raise ConflictError(str(exc)) from exc

    return SessionFeedbackResponse(
        rating=feedback.rating,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )
