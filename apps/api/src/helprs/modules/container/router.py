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

from helprs.core.dependencies import CurrentUser, DbSession, GetSettings
from helprs.core.exceptions import ConflictError, NotFoundError
from helprs.core.middleware import limiter
from helprs.core.security import fernet_decrypt
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
    create_session,
    delete_session,
    finalize_session,
    get_session_events,
    get_session_or_404,
    send_message,
    start_container,
    stop_container,
)
from helprs.modules.container.streaming import spawn_detached, stream_and_persist
from helprs.modules.installation.github import RUNNER_TOKEN_PERMISSIONS
from helprs.modules.installation.service import (
    get_byok_config,
    get_installation_by_github_id,
    mint_installation_token,
    verify_installation_access,
    verify_repo_access,
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
    installation = await get_installation_by_github_id(db, body.installation_id)
    if not installation:
        raise NotFoundError("Installation not found")

    # Installation membership is not enough: an installation can cover repos
    # this user cannot read, and the session streams the diff back to them.
    await verify_installation_access(user, installation, settings)
    await verify_repo_access(user, body.repo_full_name, settings)

    byok_config = await get_byok_config(db, installation.id)
    if not byok_config:
        raise NotFoundError("No Claude token configured for this installation")

    claude_oauth_token = fernet_decrypt(byok_config.encrypted_api_key, settings.FERNET_KEY)

    # Narrowed to this repo, read-only: the container runs Claude Code over
    # untrusted PR content with network egress.
    github_token = await mint_installation_token(
        installation.github_installation_id,
        settings,
        repositories=[body.repo_full_name.split("/")[-1]],
        permissions=RUNNER_TOKEN_PERMISSIONS,
    )

    cs = await create_session(
        db=db,
        installation_id=installation.id,
        pr_number=body.pr_number,
        repo_full_name=body.repo_full_name,
        skill_name=body.skill_name,
        user_id=user.id,
    )

    docker = _get_docker_client()
    try:
        cs = await start_container(
            db=db,
            session_id=cs.id,
            docker=docker,
            claude_oauth_token=claude_oauth_token,
            github_token=github_token,
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
    db: DbSession,
    settings: GetSettings,
    user: CurrentUser,
    offset: int = 0,
) -> StreamingResponse:
    """Relay the container's output as Server-Sent Events."""
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
        finally:
            if not finalized:
                # The client hung up mid-stream. Finalization must still run,
                # detached from this request — otherwise the session stays
                # RUNNING until the reaper mislabels it TIMEOUT, with its
                # scorecard unextracted and its PR comment never posted.
                spawn_detached(_finalize_and_close(session_id, docker))
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


async def _finalize_and_close(session_id: UUID, docker: DockerClient) -> None:
    try:
        await finalize_session(session_id, docker)
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
