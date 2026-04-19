"""Container session API routes."""

import json
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from helprs.core.config import get_settings
from helprs.core.database import get_db_context
from helprs.core.dependencies import DbSession, GetSettings, get_current_user
from helprs.core.exceptions import NotFoundError
from helprs.core.middleware import limiter
from helprs.core.security import fernet_decrypt
from helprs.modules.container.models import ContainerSession
from helprs.modules.container.pr_comment import build_session_url, extract_score_card, format_pr_comment
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
    mark_completed,
    send_message,
    start_container,
    stop_container,
    stream_and_persist,
)
from helprs.modules.installation.service import (
    get_byok_config,
    get_installation_by_github_id,
    mint_installation_token,
    post_pr_comment_with_retry,
    verify_installation_access,
    verify_session_access,
)

logger = structlog.get_logger()

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
    user=Depends(get_current_user),  # noqa: B008
):
    """Create a container session and start the container.

    Looks up the installation's BYOK credentials, mints a GitHub token,
    and provisions an ephemeral Docker container running the requested skill.
    """
    # Validate installation exists (look up by github_installation_id)
    installation = await get_installation_by_github_id(db, body.installation_id)
    if not installation:
        raise NotFoundError("Installation not found")

    # Verify user has access to this installation
    await verify_installation_access(user, installation, settings)

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
        installation_id=installation.id,
        pr_number=body.pr_number,
        repo_full_name=body.repo_full_name,
        skill_name=body.skill_name,
        user_id=user.id,
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
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
):
    """Get the current status of a container session."""
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)
    await db.refresh(cs)
    return ContainerSessionResponse.model_validate(cs)


@router.get("/sessions/{session_id}/stream")
@limiter.limit("60/minute")
async def stream_container_output(
    session_id: UUID,
    request: Request,
    db: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
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
    await verify_session_access(user, cs, db, settings)

    if cs.status != ContainerStatus.RUNNING or not cs.container_id:
        raise NotFoundError("Container is not running")

    docker = _get_docker_client()

    async def _event_stream():
        try:
            async for event in stream_and_persist(docker, cs.container_id, session_id=session_id, offset=offset):
                yield event

            # Stream ended naturally — container exited.
            # Mark session completed in DB and send done event to frontend.
            msg = "Session completed."
            status = "completed"
            try:
                async with get_db_context() as db_ctx:
                    completed = await mark_completed(db_ctx, session_id, docker)
                    status = completed.status.value
                    if completed.status == ContainerStatus.FAILED:
                        msg = "Session failed."
                    elif completed.status == ContainerStatus.COMPLETED:
                        await _post_results_comment(session_id, cs)
            except Exception:
                pass  # Best effort; cleanup task handles stragglers

            yield f"event: done\ndata: {json.dumps({'message': msg, 'status': status})}\n\n"
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
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
):
    """Retrieve persisted stream-json events for a session.

    Returns all events ordered by ``event_id``, suitable for replaying
    completed sessions in the frontend without an SSE connection.
    """
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)
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
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
):
    """Send a user message to a running container session.

    The message is forwarded to the container's Claude Code CLI stdin,
    continuing the interactive conversation.
    """
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
    user=Depends(get_current_user),  # noqa: B008
):
    """Stop a running container session."""
    cs = await get_session_or_404(db, session_id)
    await verify_session_access(user, cs, db, settings)

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


async def _post_results_comment(session_id: UUID, cs: ContainerSession) -> None:
    """Post challenge-me results to the PR as a GitHub comment (best-effort).

    Only fires for challenge-me sessions on installations with
    ``post_results_to_pr`` enabled. Mints a fresh installation token
    to handle sessions that outlive the original token's 1-hour TTL.
    """
    from helprs.modules.installation.models import Installation

    if cs.skill_name != "challenge-me":
        return

    try:
        async with get_db_context() as db:
            result = await db.execute(select(Installation).where(Installation.id == cs.installation_id))
            installation = result.scalar_one_or_none()
            if not installation or not installation.post_results_to_pr:
                return

            score_card = await extract_score_card(session_id, db)
            if not score_card:
                await logger.ainfo(
                    "post_results_no_score_card",
                    session_id=str(session_id),
                )
                return

            settings = get_settings()
            session_url = build_session_url(
                app_base_url=settings.APP_BASE_URL,
                installation_id=cs.installation_id,
                repo_full_name=cs.repo_full_name,
                pr_number=cs.pr_number,
            )
            comment_body = format_pr_comment(score_card, session_url)

            owner, repo = cs.repo_full_name.split("/", 1)
            token = await mint_installation_token(installation.github_installation_id, settings)
            await post_pr_comment_with_retry(
                owner=owner,
                repo=repo,
                pr_number=cs.pr_number,
                body=comment_body,
                installation_token=token,
            )
            await logger.ainfo(
                "post_results_comment_posted",
                session_id=str(session_id),
                pr_number=cs.pr_number,
                repo=cs.repo_full_name,
            )
    except Exception:
        await logger.aexception(
            "post_results_comment_failed",
            session_id=str(session_id),
        )
