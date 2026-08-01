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


async def cleanup_own_running(db: AsyncSession, docker: DockerClient, *, boot_id: str) -> int:
    """Stop the sessions THIS process started — used on graceful shutdown.

    Scoped by boot id rather than "everything unfinished". Several uvicorn
    workers share one Docker socket, so the unscoped version cancelled every
    peer's live sessions whenever any one worker restarted. Docker is asked
    which containers carry this process's label, because it is the authority
    on what is actually running; the database only records what was intended.
    """
    stopped = 0
    for runner in await docker.list_runners(boot_id=boot_id):
        cs = await repository.get(db, runner.session_id)
        if cs is None or cs.completed_at is not None:
            continue
        await _destroy(docker, cs)
        cs.status = ContainerStatus.CANCELLED
        cs.completed_at = datetime.now(UTC)
        stopped += 1

    if stopped:
        await db.flush()
        await logger.ainfo("shutdown_sessions_stopped", count=stopped, boot_id=boot_id)
    return stopped


async def reconcile_stale_sessions(db: AsyncSession, docker: DockerClient) -> int:
    """Fail sessions whose container is gone.

    Asks Docker rather than assuming, because "unfinished at boot" is not the
    same as "dead": with several workers a RUNNING row usually belongs to a
    peer that is still streaming it, and marking those FAILED killed live
    sessions every time one worker restarted.

    A row with no container id never got that far, so nothing is running for
    it either way.
    """
    stale = []
    for cs in await repository.list_unfinished(db):
        if cs.container_id and await docker.container_is_running(cs.container_id):
            continue
        stale.append(cs)

    for cs in stale:
        cs.status = ContainerStatus.FAILED
        cs.completed_at = datetime.now(UTC)

    if stale:
        await db.flush()
        await logger.ainfo("stale_sessions_reconciled", count=len(stale))
    return len(stale)
