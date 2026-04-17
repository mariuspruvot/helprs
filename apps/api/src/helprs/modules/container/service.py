"""Container orchestration business logic.

Manages the lifecycle of ephemeral Docker containers that run Claude Code CLI
skills against pull requests. Uses aiodocker for async Docker API interaction.

Containers run in bidirectional stream-json mode: the initial skill prompt is
sent as the first message, and subsequent user messages are written to the
container's stdin via a FIFO. Output is streamed from stdout.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import structlog
from sqlalchemy import select

from helprs.core.exceptions import ExternalServiceError, NotFoundError
from helprs.modules.container.models import ContainerSession, ContainerStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Container TTL: 15 minutes maximum
CONTAINER_TTL_SECONDS = 15 * 60

# Base image for the claude-runner container
CLAUDE_RUNNER_IMAGE = "helprs/claude-runner:latest"

# Path where skills are located on the host
SKILLS_BASE_PATH = Path(__file__).resolve().parents[5] / "skills"


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
        """Write data to the container's stdin via exec."""
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
        container = await self._docker.containers.create_container(config)
        return container["Id"]

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
        async for line in container.log(stdout=True, stderr=True, follow=follow):
            yield line

    async def write_to_container(self, container_id: str, data: str) -> None:
        """Write a message to the container's FIFO via docker exec.

        The entrypoint reads from /tmp/claude-input FIFO, so we write there.
        """
        container = await self._docker.containers.get(container_id)
        exec_obj = await container.exec(
            cmd=["bash", "-c", f"echo {json.dumps(data)} > /tmp/claude-input"],
            stdout=False,
            stderr=False,
        )
        await exec_obj.start()

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

    volumes = [
        f"{skill_path}:/skills/{cs.skill_name}:ro",
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


async def stream_output(
    docker: DockerClient,
    container_id: str,
) -> AsyncIterator[str]:
    """Async generator yielding container log lines as SSE events."""
    async for line in docker.container_logs(container_id, follow=True):
        yield f"data: {line}\n\n"


async def send_message(
    db: AsyncSession,
    session_id: UUID,
    docker: DockerClient,
    content: str,
) -> None:
    """Send a user message to a running container session.

    Writes a stream-json formatted message to the container's FIFO,
    which Claude Code CLI reads as the next user turn.
    """
    cs = await get_session_or_404(db, session_id)

    if cs.status != ContainerStatus.RUNNING or not cs.container_id:
        raise ExternalServiceError("Container is not running")

    message = json.dumps({
        "type": "user",
        "message": {"role": "user", "content": content},
    })

    try:
        await docker.write_to_container(cs.container_id, message)
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
) -> ContainerSession:
    """Wait for the container to finish, capture exit code, clean up."""
    cs = await get_session_or_404(db, session_id)

    if cs.status != ContainerStatus.RUNNING or not cs.container_id:
        return cs

    try:
        exit_code = await asyncio.wait_for(
            docker.wait_container(cs.container_id),
            timeout=CONTAINER_TTL_SECONDS,
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
) -> int:
    """Find sessions past TTL and destroy their containers.

    Returns the number of sessions cleaned up.
    """
    cutoff = datetime.now(UTC).timestamp() - CONTAINER_TTL_SECONDS
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
