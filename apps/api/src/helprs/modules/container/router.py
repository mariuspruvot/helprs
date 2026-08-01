"""Container session API routes.

Handlers resolve the session, authorize the caller, call one use case and
shape the response. The one exception is the SSE endpoint, which owns a
streaming response rather than a value.
"""

import json
from uuid import UUID

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from helprs.core.database import get_db_context
from helprs.core.dependencies import CurrentUser, DbSession, GetSettings, authenticate_token, stream_token
from helprs.core.exceptions import ConflictError
from helprs.core.middleware import limiter
from helprs.modules.container.docker_client import AioDockerClient, DockerClient
from helprs.modules.container.models import ContainerStatus
from helprs.modules.container.schemas import (
    ContainerSessionResponse,
    CreateSessionRequest,
    ScorecardResponse,
    SendMessageRequest,
    SendMessageResponse,
    SessionEventResponse,
    SessionEventsListResponse,
    StopSessionResponse,
)
from helprs.modules.container.service import (
    delete_session,
    finalize_session,
    get_session_events,
    get_session_or_404,
    open_session,
    send_message,
    stop_container,
)
from helprs.modules.container.streaming import spawn_detached, stream_and_persist
from helprs.modules.installation.service import (
    verify_session_access,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/containers", tags=["containers"])


def _get_docker_client() -> DockerClient:
    """Provide the Docker client dependency."""
    return AioDockerClient()


@router.post("/sessions", response_model=ContainerSessionResponse, status_code=201)
@limiter.limit("10/minute")
async def create_container_session(
    body: CreateSessionRequest,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> ContainerSessionResponse:
    """Create a session and start its container."""
    docker = _get_docker_client()
    try:
        cs = await open_session(
            db,
            docker,
            user=user,
            installation_github_id=body.installation_id,
            pr_number=body.pr_number,
            repo_full_name=body.repo_full_name,
            skill_name=body.skill_name,
            settings=settings,
        )
    finally:
        await docker.close()

    await db.refresh(cs)
    return ContainerSessionResponse.model_validate(cs)


@router.get("/sessions/{session_id}", response_model=ContainerSessionResponse)
@limiter.limit("30/minute")
async def get_container_session(
    session_id: UUID,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> ContainerSessionResponse:
    """Current status of a session."""
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)
    await db.refresh(cs)
    return ContainerSessionResponse.model_validate(cs)


def _resume_offset(request: Request, offset: int) -> int:
    """Where to resume from: explicit offset, else EventSource's header.

    Native ``EventSource`` reconnects send ``Last-Event-ID`` rather than a
    query parameter, and cannot set custom headers on the way out.
    """
    if offset:
        return offset
    last_event_id = request.headers.get("last-event-id", "")
    return int(last_event_id) if last_event_id.isdigit() else 0


@router.get("/sessions/{session_id}/stream")
@limiter.limit("60/minute")
async def stream_container_output(
    session_id: UUID,
    request: Request,
    settings: GetSettings,
    offset: int = 0,
) -> StreamingResponse:
    """Relay the container's output as Server-Sent Events.

    Deliberately takes no ``DbSession`` and no user dependency. FastAPI tears
    yield-dependencies down only once the streaming body completes, so any
    ``Depends(get_db)`` here -- including the one behind an authentication
    dependency -- would keep a pooled connection, and an open transaction,
    checked out for the life of the stream: up to CONTAINER_TTL_SECONDS. The
    pool is DB_POOL_SIZE + DB_MAX_OVERFLOW per worker, so a handful of
    viewers would starve every other request on that worker, and each
    idle-in-transaction backend blocks VACUUM. Authentication and
    authorization run in a short session that closes before streaming starts.
    """
    async with get_db_context() as db:
        user = await authenticate_token(db, settings, stream_token(request))
        cs = await get_session_or_404(db, session_id)
        await verify_session_access(user, cs, db, settings)

        if cs.status != ContainerStatus.RUNNING or not cs.container_id:
            raise ConflictError("Container is not running")

        container_id = cs.container_id

    resume_from = _resume_offset(request, offset)
    docker = _get_docker_client()

    async def _event_stream():
        finalized = False
        try:
            async for event in stream_and_persist(docker, container_id, session_id=session_id, offset=resume_from):
                yield event

            # Stream ended on its own: the container exited.
            status = await finalize_session(session_id, docker)
            finalized = True
            yield _done_event(status)
        except Exception:
            # The response has already started, so there is no status code
            # left to change. Without a frame here the client just sees a
            # truncated body, and native EventSource silently reconnects
            # into the same failure.
            logger.exception("sse_stream_failed", session_id=str(session_id))
            yield _error_event("Streaming failed. The session will be finalized in the background.")
        finally:
            if not finalized:
                # The client hung up, or the stream broke, mid-session. Both
                # the drain and the finalization have to continue detached
                # from this request. Detaching only the finalization -- as
                # this did before -- stops the drain the moment the tab
                # closes, so finalize_session then builds its scorecard from
                # a truncated event history and posts that to the PR, quietly
                # defeating the thing detaching was meant to protect.
                spawn_detached(_drain_and_finalize(session_id, container_id, docker))
            else:
                await docker.close()

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _done_event(status: ContainerStatus) -> str:
    message = {
        ContainerStatus.COMPLETED: "Session completed.",
        ContainerStatus.FAILED: "Session failed.",
        ContainerStatus.TIMEOUT: "Session timed out.",
        ContainerStatus.CANCELLED: "Session cancelled.",
    }.get(status, "Session completed.")
    return f"event: done\ndata: {json.dumps({'message': message, 'status': status.value})}\n\n"


def _error_event(message: str) -> str:
    return f"event: error\ndata: {json.dumps({'message': message})}\n\n"


async def _drain_and_finalize(session_id: UUID, container_id: str, docker: DockerClient) -> None:
    """Finish the session with no client attached.

    Keeps consuming the container's output until it exits, then finalizes.
    Re-reading the log from the start is deliberate and cheap: ``_persist``
    is idempotent through ``ON CONFLICT DO NOTHING``, and nothing is being
    yielded to anyone, so the offset does not matter here.
    """
    try:
        async for _ in stream_and_persist(docker, container_id, session_id=session_id):
            pass
        await finalize_session(session_id, docker)
    except Exception:
        await logger.aexception("detached_finalize_failed", session_id=str(session_id))
    finally:
        await docker.close()


@router.get("/sessions/{session_id}/events", response_model=SessionEventsListResponse)
@limiter.limit("30/minute")
async def get_session_events_endpoint(
    session_id: UUID,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> SessionEventsListResponse:
    """Persisted events for a session, for replaying it without SSE."""
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)

    events = await get_session_events(db, session_id)
    return SessionEventsListResponse(
        session_id=session_id,
        events=[SessionEventResponse.model_validate(e) for e in events],
        total=len(events),
    )


@router.get("/sessions/{session_id}/scorecard", response_model=ScorecardResponse)
@limiter.limit("30/minute")
async def get_session_scorecard(
    session_id: UUID,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> ScorecardResponse:
    """The parsed scorecard of a completed session."""
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)
    return ScorecardResponse(session_id=session_id, scorecard=cs.scorecard, xp_earned=cs.xp_earned)


@router.post("/sessions/{session_id}/message", response_model=SendMessageResponse)
@limiter.limit("30/minute")
async def send_session_message(
    session_id: UUID,
    body: SendMessageRequest,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> SendMessageResponse:
    """Forward a user message into the running conversation."""
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)

    docker = _get_docker_client()
    try:
        await send_message(db=db, session_id=session_id, docker=docker, content=body.content)
    finally:
        await docker.close()

    return SendMessageResponse(
        session_id=session_id,
        status="sent",
        message="Message delivered to container",
    )


@router.post("/sessions/{session_id}/stop", response_model=StopSessionResponse)
@limiter.limit("10/minute")
async def stop_container_session(
    session_id: UUID,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> StopSessionResponse:
    """Abort a running session."""
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)

    docker = _get_docker_client()
    try:
        cs = await stop_container(db=db, session_id=session_id, docker=docker)
    finally:
        await docker.close()

    return StopSessionResponse(id=cs.id, status=cs.status.value, message=f"Session {cs.status.value}")


@router.delete("/sessions/{session_id}", status_code=204)
@limiter.limit("10/minute")
async def delete_container_session(
    session_id: UUID,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> Response:
    """Delete a session and its events."""
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)

    await delete_session(db=db, session_id=session_id)
    return Response(status_code=204)
