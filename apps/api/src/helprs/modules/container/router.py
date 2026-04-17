"""Container session API routes."""

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from helprs.core.dependencies import DbSession, GetSettings
from helprs.core.exceptions import NotFoundError
from helprs.core.middleware import limiter
from helprs.core.security import fernet_decrypt
from helprs.modules.container.schemas import (
    ContainerSessionResponse,
    CreateSessionRequest,
    SendMessageRequest,
    SendMessageResponse,
    SessionEventResponse,
    SessionEventsListResponse,
    StopSessionResponse,
)
from helprs.modules.container.service import (
    AioDockerClient,
    ContainerStatus,
    create_session,
    get_session_events,
    get_session_or_404,
    send_message,
    start_container,
    stop_container,
    stream_and_persist,
)
from helprs.modules.installation.service import get_byok_config, mint_installation_token

router = APIRouter(prefix="/containers", tags=["containers"])


def _get_docker_client() -> AioDockerClient:
    """Provide the Docker client dependency."""
    return AioDockerClient()


@router.post("/sessions", response_model=ContainerSessionResponse, status_code=201)
@limiter.limit("10/minute")
async def create_container_session(
    body: CreateSessionRequest,
    request: Request,
    db: DbSession,
    settings: GetSettings,
):
    """Create a container session and start the container.

    Looks up the installation's BYOK credentials, mints a GitHub token,
    and provisions an ephemeral Docker container running the requested skill.
    """
    from sqlalchemy import select

    from helprs.modules.installation.models import Installation

    # Validate installation exists
    result = await db.execute(
        select(Installation).where(
            Installation.id == body.installation_id,
            Installation.deleted_at.is_(None),
        )
    )
    installation = result.scalar_one_or_none()
    if not installation:
        raise NotFoundError("Installation not found")

    # Get stored Claude OAuth token (from claude setup-token)
    byok_config = await get_byok_config(db, installation.id)
    if not byok_config:
        raise NotFoundError("No Claude token configured for this installation")

    claude_oauth_token = fernet_decrypt(byok_config.encrypted_api_key, settings.FERNET_KEY)

    # Mint GitHub installation token
    github_token = await mint_installation_token(installation.github_installation_id, settings)

    # Create session record
    cs = await create_session(
        db=db,
        installation_id=body.installation_id,
        pr_number=body.pr_number,
        repo_full_name=body.repo_full_name,
        skill_name=body.skill_name,
    )

    # Start the container
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
):
    """Get the current status of a container session."""
    cs = await get_session_or_404(db, session_id)
    await db.refresh(cs)
    return ContainerSessionResponse.model_validate(cs)


@router.get("/sessions/{session_id}/stream")
@limiter.limit("60/minute")
async def stream_container_output(
    session_id: UUID,
    request: Request,
    db: DbSession,
    offset: int = 0,
):
    """SSE endpoint streaming container stdout/stderr.

    Accepts an ``offset`` query parameter: the number of events to skip.
    Clients should pass the last received event ``id`` so that reconnects
    resume from where they left off instead of replaying the full log.

    Also reads the ``Last-Event-ID`` header (sent automatically by
    EventSource on native auto-reconnect) as a fallback when the query
    parameter is absent or zero.
    """
    # EventSource auto-reconnect sends Last-Event-ID header, not query params.
    if offset == 0:
        last_event_id = request.headers.get("last-event-id", "")
        if last_event_id.isdigit():
            offset = int(last_event_id)

    cs = await get_session_or_404(db, session_id)

    if cs.status != ContainerStatus.RUNNING or not cs.container_id:
        raise NotFoundError("Container is not running")

    docker = _get_docker_client()

    async def _event_stream():
        try:
            async for event in stream_and_persist(docker, cs.container_id, session_id=session_id, offset=offset):
                yield event
        finally:
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


@router.get("/sessions/{session_id}/events", response_model=SessionEventsListResponse)
@limiter.limit("30/minute")
async def get_session_events_endpoint(
    session_id: UUID,
    request: Request,
    db: DbSession,
):
    """Retrieve persisted stream-json events for a session.

    Returns all events ordered by ``event_id``, suitable for replaying
    completed sessions in the frontend without an SSE connection.
    """
    events = await get_session_events(db, session_id)
    return SessionEventsListResponse(
        session_id=session_id,
        events=[SessionEventResponse.model_validate(e) for e in events],
        total=len(events),
    )


@router.post("/sessions/{session_id}/message", response_model=SendMessageResponse)
@limiter.limit("30/minute")
async def send_session_message(
    session_id: UUID,
    body: SendMessageRequest,
    request: Request,
    db: DbSession,
):
    """Send a user message to a running container session.

    The message is forwarded to the container's Claude Code CLI stdin,
    continuing the interactive conversation.
    """
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
):
    """Stop a running container session."""
    docker = _get_docker_client()
    try:
        cs = await stop_container(db=db, session_id=session_id, docker=docker)
    finally:
        await docker.close()

    return StopSessionResponse(
        id=cs.id,
        status=cs.status.value,
        message=f"Session {cs.status.value}",
    )
