"""Reaping containers the happy path did not clean up.

Three jobs, all idempotent so several workers can run them concurrently:
expiry (TTL passed), shutdown (stop everything), and boot reconciliation
(rows left RUNNING by a process that died).
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.container import repository
from helprs.modules.container.docker_client import DockerClient
from helprs.modules.container.models import ContainerSession, ContainerStatus

logger = structlog.get_logger()


async def _destroy(docker: DockerClient, cs: ContainerSession) -> None:
    """Best-effort teardown: a container that is already gone is a success."""
    if not cs.container_id:
        return
    try:
        await docker.stop_container(cs.container_id)
        await docker.remove_container(cs.container_id, force=True)
    except Exception as exc:
        await logger.awarning("cleanup_container_failed", session_id=str(cs.id), error=str(exc))


async def cleanup_expired(db: AsyncSession, docker: DockerClient, *, ttl_seconds: int) -> int:
    """Destroy containers whose session outlived its TTL. Returns the count."""
    cutoff = datetime.now(UTC) - timedelta(seconds=ttl_seconds)
    expired = await repository.list_unfinished(db, created_before=cutoff)

    for cs in expired:
        await _destroy(docker, cs)
        cs.status = ContainerStatus.TIMEOUT
        cs.completed_at = datetime.now(UTC)

    if expired:
        await db.flush()
        await logger.ainfo("expired_sessions_cleaned", count=len(expired))
    return len(expired)


async def cleanup_all_running(db: AsyncSession, docker: DockerClient) -> int:
    """Stop every live session — used on graceful shutdown."""
    sessions = await repository.list_unfinished(db)

    for cs in sessions:
        await _destroy(docker, cs)
        cs.status = ContainerStatus.CANCELLED
        cs.completed_at = datetime.now(UTC)

    if sessions:
        await db.flush()
        await logger.ainfo("shutdown_sessions_stopped", count=len(sessions))
    return len(sessions)


async def reconcile_stale_sessions(db: AsyncSession) -> int:
    """Fail sessions left RUNNING by a crashed process.

    Their containers died with the host process, so waiting for the TTL would
    only leave the dashboard lying for 15 minutes.
    """
    stale = await repository.list_unfinished(db)

    for cs in stale:
        cs.status = ContainerStatus.FAILED
        cs.completed_at = datetime.now(UTC)

    if stale:
        await db.flush()
        await logger.ainfo("stale_sessions_reconciled", count=len(stale))
    return len(stale)
