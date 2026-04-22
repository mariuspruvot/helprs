"""Container orchestration business logic.

Manages the lifecycle of ephemeral Docker containers that run Claude Code CLI
skills against pull requests. Uses aiodocker for async Docker API interaction.

Containers run in bidirectional stream-json mode: the initial skill prompt is
sent as the first message, and subsequent user messages are written to the
container's stdin via a FIFO. Output is streamed from stdout.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import structlog
from sqlalchemy import select

from helprs.core.database import get_db_context
from helprs.core.exceptions import ExternalServiceError, NotFoundError
from helprs.modules.container.models import ContainerSession, ContainerStatus, SessionEvent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Default container TTL (overridden by Settings.CONTAINER_TTL_SECONDS)
_DEFAULT_CONTAINER_TTL_SECONDS = 15 * 60

# Base image for the claude-runner container
CLAUDE_RUNNER_IMAGE = "claude-runner:latest"

# Path where skills are located inside THIS container (for validation).
# In Docker: /app/skills. Locally: repo root relative to this file.
_LOCAL_SKILLS_PATH = Path(__file__).resolve().parents[5] / "skills"
_DOCKER_SKILLS_PATH = Path("/app/skills")
SKILLS_BASE_PATH = _DOCKER_SKILLS_PATH if _DOCKER_SKILLS_PATH.exists() else _LOCAL_SKILLS_PATH

# Host path for skills — needed for Docker-in-Docker volume mounts.
# The API container can't use its own /app/skills path as a bind mount source
# for child containers; Docker needs the HOST filesystem path.
SKILLS_HOST_PATH = os.environ.get("SKILLS_HOST_PATH", str(SKILLS_BASE_PATH))


class DockerClient(Protocol):
    """Protocol for the Docker client used by the container service.

    Abstracts the Docker SDK so tests can provide a simple test double.
    """

    async def create_container(
        self,
        image: str,
        environment: dict[str, str],
        volumes: list[str],
        labels: dict[str, str],
    ) -> str:
        """Create a container with stdin enabled and return its ID."""
        ...

    async def start_container(self, container_id: str) -> None:
        """Start a created container."""
        ...

    async def stop_container(self, container_id: str) -> None:
        """Stop a running container."""
        ...

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        """Remove a container."""
        ...

    async def container_logs(self, container_id: str, follow: bool = False) -> AsyncIterator[str]:
        """Stream container logs."""
        ...

    async def write_to_container(self, container_id: str, data: str) -> None:
        """Write data to the container's FIFO via exec."""
        ...

    async def wait_container(self, container_id: str) -> int:
        """Wait for a container to exit. Returns exit code."""
        ...


class AioDockerClient:
    """Production Docker client wrapping aiodocker."""

    def __init__(self) -> None:
        import aiodocker

        self._docker = aiodocker.Docker()

    async def create_container(
        self,
        image: str,
        environment: dict[str, str],
        volumes: list[str],
        labels: dict[str, str],
    ) -> str:
        env_list = [f"{k}={v}" for k, v in environment.items()]
        binds = volumes
        config = {
            "Image": image,
            "Env": env_list,
            "Labels": labels,
            "OpenStdin": True,
            "HostConfig": {
                "Binds": binds,
                "Memory": 512 * 1024 * 1024,  # 512MB
                "NanoCPUs": 1_000_000_000,  # 1 CPU
                "NetworkMode": "bridge",
            },
        }
        container = await self._docker.containers.create(config)
        return container.id

    async def start_container(self, container_id: str) -> None:
        container = await self._docker.containers.get(container_id)
        await container.start()

    async def stop_container(self, container_id: str) -> None:
        container = await self._docker.containers.get(container_id)
        await container.stop()

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        container = await self._docker.containers.get(container_id)
        await container.delete(force=force)

    async def container_logs(self, container_id: str, follow: bool = False) -> AsyncIterator[str]:
        container = await self._docker.containers.get(container_id)
        # Only read stdout — Claude Code writes stream-json to stdout.
        # stderr contains verbose/diagnostic output that duplicates events.
        async for line in container.log(stdout=True, stderr=False, follow=follow):
            yield line

    async def write_to_container(self, container_id: str, data: str) -> None:
        """Write data to the container's FIFO via docker exec.

        The entrypoint reads newline-terminated lines from /tmp/claude-input.
        Uses base64 encoding to safely pass arbitrary text through the shell
        without risking interpretation of special characters ($, `, !, etc.).
        A trailing newline is always appended so ``read`` in the entrypoint
        loop receives a complete line.
        """
        container = await self._docker.containers.get(container_id)
        encoded = base64.b64encode((data + "\n").encode()).decode()
        exec_obj = await container.exec(
            cmd=["sh", "-c", f"echo {encoded} | base64 -d > /tmp/claude-input"],
        )
        await exec_obj.start(detach=True)

    async def wait_container(self, container_id: str) -> int:
        container = await self._docker.containers.get(container_id)
        result = await container.wait()
        return result["StatusCode"]

    async def close(self) -> None:
        await self._docker.close()


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


async def create_session(
    db: AsyncSession,
    installation_id: UUID,
    pr_number: int,
    repo_full_name: str,
    skill_name: str,
    user_id: UUID | None = None,
) -> ContainerSession:
    """Create a new container session record in pending state."""
    session = ContainerSession(
        installation_id=installation_id,
        user_id=user_id,
        pr_number=pr_number,
        repo_full_name=repo_full_name,
        skill_name=skill_name,
        status=ContainerStatus.PENDING,
    )
    db.add(session)
    await db.flush()
    await logger.ainfo(
        "container_session_created",
        session_id=str(session.id),
        repo=repo_full_name,
        pr=pr_number,
        skill=skill_name,
    )
    return session


async def get_session(db: AsyncSession, session_id: UUID) -> ContainerSession | None:
    """Look up a container session by ID."""
    result = await db.execute(select(ContainerSession).where(ContainerSession.id == session_id))
    return result.scalar_one_or_none()


async def get_session_or_404(db: AsyncSession, session_id: UUID) -> ContainerSession:
    """Look up a container session by ID, raising NotFoundError if missing."""
    session = await get_session(db, session_id)
    if session is None:
        raise NotFoundError("Container session not found")
    return session


# ---------------------------------------------------------------------------
# Container lifecycle
# ---------------------------------------------------------------------------


async def start_container(
    db: AsyncSession,
    session_id: UUID,
    docker: DockerClient,
    claude_oauth_token: str,
    github_token: str,
    skills_base_path: Path | None = None,
) -> ContainerSession:
    """Provision and start a Docker container for the given session.

    Transitions the session from PENDING -> RUNNING.
    """
    cs = await get_session_or_404(db, session_id)

    if cs.status != ContainerStatus.PENDING:
        raise ExternalServiceError(f"Cannot start session in '{cs.status.value}' state")

    resolved_base = skills_base_path if skills_base_path is not None else SKILLS_BASE_PATH
    skill_path = resolved_base / cs.skill_name
    if not skill_path.is_dir():
        cs.status = ContainerStatus.FAILED
        await db.flush()
        raise NotFoundError(f"Skill '{cs.skill_name}' not found")

    environment = {
        "CLAUDE_CODE_OAUTH_TOKEN": claude_oauth_token,
        "GITHUB_TOKEN": github_token,
        "SKILL_NAME": cs.skill_name,
        "PR_NUMBER": str(cs.pr_number),
        "REPO_FULL_NAME": cs.repo_full_name,
    }

    # Use HOST path for volume mount (Docker-in-Docker requires host paths)
    host_skill_path = f"{SKILLS_HOST_PATH}/{cs.skill_name}"
    volumes = [
        f"{host_skill_path}:/skills/{cs.skill_name}:ro",
    ]

    labels = {
        "helprs.session_id": str(cs.id),
        "helprs.skill": cs.skill_name,
        "helprs.repo": cs.repo_full_name,
    }

    try:
        container_id = await docker.create_container(
            image=CLAUDE_RUNNER_IMAGE,
            environment=environment,
            volumes=volumes,
            labels=labels,
        )
        await docker.start_container(container_id)
    except Exception as exc:
        cs.status = ContainerStatus.FAILED
        await db.flush()
        await logger.aerror(
            "container_start_failed",
            session_id=str(session_id),
            error=str(exc),
        )
        raise ExternalServiceError(f"Failed to start container: {exc}") from exc

    cs.container_id = container_id
    cs.status = ContainerStatus.RUNNING
    cs.started_at = datetime.now(UTC)
    await db.flush()

    await logger.ainfo(
        "container_started",
        session_id=str(session_id),
        container_id=container_id,
    )
    return cs


async def stream_events(
    docker: DockerClient,
    container_id: str,
) -> AsyncIterator[tuple[int, str]]:
    """Yield ``(event_id, raw_line)`` tuples from container log stream.

    Handles Docker log frame buffering (long lines split across chunks),
    newline splitting, and keepalive signaling.

    Yields ``(0, "")`` as a sentinel for keepalive intervals (no data
    from container for 15 seconds — Claude is thinking).

    IMPORTANT: We must NOT use ``asyncio.wait_for()`` on the log iterator.
    aiodocker uses a multiplexed stream format (8-byte header + payload)
    with ``readexactly()`` calls.  Cancelling a ``readexactly()`` mid-read
    corrupts the stream position, causing all subsequent reads to
    desynchronize and silently drop events.  Instead we keep the read task
    alive across keepalive intervals using ``asyncio.wait()``.
    """
    keepalive_interval = 15.0
    event_id = 0
    buffer = ""

    log_iter = docker.container_logs(container_id, follow=True).__aiter__()
    read_task: asyncio.Task[str] | None = None
    try:
        while True:
            if read_task is None:
                read_task = asyncio.ensure_future(log_iter.__anext__())

            done, _ = await asyncio.wait({read_task}, timeout=keepalive_interval)

            if not done:
                # Timeout — no data arrived, but keep the read task alive.
                yield (0, "")
                continue

            try:
                chunk = read_task.result()
            except StopAsyncIteration:
                read_task = None
                break

            read_task = None
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                event_id += 1
                yield (event_id, line)
    finally:
        if read_task is not None:
            read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await read_task

    # Flush any remaining content in the buffer (e.g. the final result
    # event if Docker closed the stream before flushing the trailing \n).
    if buffer:
        line = buffer.strip()
        if line:
            event_id += 1
            yield (event_id, line)


async def stream_output(
    docker: DockerClient,
    container_id: str,
    offset: int = 0,
) -> AsyncIterator[str]:
    """Yield SSE-formatted events without persistence.

    Thin wrapper over :func:`stream_events` that formats tuples as SSE.
    Used by tests and code paths that don't need DB persistence.
    """
    async for event_id, line in stream_events(docker, container_id):
        if event_id == 0:
            yield ": keepalive\n\n"
            continue
        if event_id <= offset:
            continue
        yield f"id: {event_id}\ndata: {line}\n\n"


_PERSIST_BATCH_SIZE = 10


async def stream_and_persist(
    docker: DockerClient,
    container_id: str,
    session_id: UUID,
    offset: int = 0,
    batch_size: int = _PERSIST_BATCH_SIZE,
) -> AsyncIterator[str]:
    """Stream container output as SSE while persisting events to the DB.

    Wraps :func:`stream_events`, yields the same SSE format as
    :func:`stream_output`, but also batch-inserts events into the
    ``session_events`` table via :func:`get_db_context`.

    Events at or below *offset* are skipped for SSE output but still
    persisted (they may not have been flushed before a prior disconnect).
    Duplicate ``(session_id, event_id)`` pairs are silently ignored via
    ``ON CONFLICT DO NOTHING``.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    pending: list[tuple[int, dict]] = []

    async def _flush() -> None:
        if not pending:
            return
        batch = pending[:]
        pending.clear()
        try:
            async with get_db_context() as db:
                stmt = pg_insert(SessionEvent.__table__).values(
                    [{"session_id": session_id, "event_id": eid, "data": data} for eid, data in batch]
                )
                stmt = stmt.on_conflict_do_nothing(
                    constraint="uq_session_events_session_event",
                )
                await db.execute(stmt)
        except Exception:
            await logger.aexception(
                "event_persist_failed",
                session_id=str(session_id),
                batch_size=len(batch),
            )

    async for event_id, line in stream_events(docker, container_id):
        if event_id == 0:
            # Keepalive — flush pending if any
            await _flush()
            yield ": keepalive\n\n"
            continue

        # Parse to JSONB-safe dict
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            parsed = {"_raw": line}

        pending.append((event_id, parsed))

        if len(pending) >= batch_size:
            await _flush()

        if event_id <= offset:
            continue
        yield f"id: {event_id}\ndata: {line}\n\n"

    # Final flush for remaining events
    await _flush()


# ---------------------------------------------------------------------------
# Session event retrieval
# ---------------------------------------------------------------------------


async def get_session_events(
    db: AsyncSession,
    session_id: UUID,
) -> list[SessionEvent]:
    """Return all persisted events for a session, ordered by event_id."""
    await get_session_or_404(db, session_id)
    result = await db.execute(
        select(SessionEvent).where(SessionEvent.session_id == session_id).order_by(SessionEvent.event_id)
    )
    return list(result.scalars().all())


async def delete_session(db: AsyncSession, session_id: UUID) -> None:
    """Delete a container session and its events (CASCADE)."""
    session = await get_session_or_404(db, session_id)
    await db.delete(session)
    await db.flush()


async def send_message(
    db: AsyncSession,
    session_id: UUID,
    docker: DockerClient,
    content: str,
) -> None:
    """Send a user message to a running container session.

    Writes the raw user content to the container's FIFO (newline-terminated).
    The entrypoint reads each line and invokes ``claude -c -p`` to continue
    the conversation.
    """
    cs = await get_session_or_404(db, session_id)

    if cs.status != ContainerStatus.RUNNING or not cs.container_id:
        raise ExternalServiceError("Container is not running")

    try:
        await docker.write_to_container(cs.container_id, content)
    except Exception as exc:
        await logger.aerror(
            "container_message_failed",
            session_id=str(session_id),
            error=str(exc),
        )
        raise ExternalServiceError(f"Failed to send message to container: {exc}") from exc

    await logger.ainfo(
        "container_message_sent",
        session_id=str(session_id),
    )


async def stop_container(
    db: AsyncSession,
    session_id: UUID,
    docker: DockerClient,
) -> ContainerSession:
    """Stop and remove the container for a session.

    Transitions the session to COMPLETED (if running) or leaves it unchanged.
    """
    cs = await get_session_or_404(db, session_id)

    if cs.status not in (ContainerStatus.RUNNING, ContainerStatus.PENDING):
        return cs

    if cs.container_id:
        try:
            await docker.stop_container(cs.container_id)
            await docker.remove_container(cs.container_id, force=True)
        except Exception as exc:
            await logger.awarning(
                "container_stop_failed",
                session_id=str(session_id),
                container_id=cs.container_id,
                error=str(exc),
            )

    cs.status = ContainerStatus.COMPLETED
    cs.completed_at = datetime.now(UTC)
    await db.flush()

    await logger.ainfo(
        "container_stopped",
        session_id=str(session_id),
    )
    return cs


async def mark_completed(
    db: AsyncSession,
    session_id: UUID,
    docker: DockerClient,
    ttl_seconds: int = _DEFAULT_CONTAINER_TTL_SECONDS,
) -> ContainerSession:
    """Wait for the container to finish, capture exit code, clean up."""
    cs = await get_session_or_404(db, session_id)

    if cs.status != ContainerStatus.RUNNING or not cs.container_id:
        return cs

    try:
        exit_code = await asyncio.wait_for(
            docker.wait_container(cs.container_id),
            timeout=ttl_seconds,
        )
        cs.status = ContainerStatus.COMPLETED if exit_code == 0 else ContainerStatus.FAILED
    except TimeoutError:
        cs.status = ContainerStatus.TIMEOUT
        await logger.awarning("container_timeout", session_id=str(session_id))
    finally:
        cs.completed_at = datetime.now(UTC)
        if cs.container_id:
            with contextlib.suppress(Exception):
                await docker.remove_container(cs.container_id, force=True)
        await db.flush()

    return cs


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def cleanup_expired(
    db: AsyncSession,
    docker: DockerClient,
    ttl_seconds: int = _DEFAULT_CONTAINER_TTL_SECONDS,
) -> int:
    """Find sessions past TTL and destroy their containers.

    Returns the number of sessions cleaned up.
    """
    cutoff = datetime.now(UTC).timestamp() - ttl_seconds
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=UTC)

    result = await db.execute(
        select(ContainerSession).where(
            ContainerSession.status.in_([ContainerStatus.RUNNING, ContainerStatus.PENDING]),
            ContainerSession.created_at < cutoff_dt,
        )
    )
    expired = list(result.scalars().all())

    cleaned = 0
    for cs in expired:
        if cs.container_id:
            try:
                await docker.stop_container(cs.container_id)
                await docker.remove_container(cs.container_id, force=True)
            except Exception as exc:
                await logger.awarning(
                    "cleanup_container_failed",
                    session_id=str(cs.id),
                    error=str(exc),
                )
        cs.status = ContainerStatus.TIMEOUT
        cs.completed_at = datetime.now(UTC)
        cleaned += 1

    if cleaned:
        await db.flush()
        await logger.ainfo("expired_sessions_cleaned", count=cleaned)

    return cleaned


async def cleanup_all_running(
    db: AsyncSession,
    docker: DockerClient,
) -> int:
    """Stop ALL running/pending sessions. Used during graceful shutdown."""
    result = await db.execute(
        select(ContainerSession).where(
            ContainerSession.status.in_([ContainerStatus.RUNNING, ContainerStatus.PENDING]),
        )
    )
    sessions = list(result.scalars().all())

    cleaned = 0
    for cs in sessions:
        if cs.container_id:
            with contextlib.suppress(Exception):
                await docker.stop_container(cs.container_id)
                await docker.remove_container(cs.container_id, force=True)
        cs.status = ContainerStatus.COMPLETED
        cs.completed_at = datetime.now(UTC)
        cleaned += 1

    if cleaned:
        await db.flush()
        await logger.ainfo("shutdown_sessions_stopped", count=cleaned)

    return cleaned


async def reconcile_stale_sessions(db: AsyncSession) -> int:
    """Mark any RUNNING/PENDING sessions as FAILED on boot.

    After a crash, containers are gone but DB records still show RUNNING.
    This reconciles them immediately rather than waiting for TTL expiry.
    """
    result = await db.execute(
        select(ContainerSession).where(
            ContainerSession.status.in_([ContainerStatus.RUNNING, ContainerStatus.PENDING]),
        )
    )
    stale = list(result.scalars().all())

    for cs in stale:
        cs.status = ContainerStatus.FAILED
        cs.completed_at = datetime.now(UTC)

    if stale:
        await db.flush()
        await logger.ainfo("stale_sessions_reconciled", count=len(stale))

    return len(stale)
