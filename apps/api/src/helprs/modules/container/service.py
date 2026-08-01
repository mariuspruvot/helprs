"""Container session use cases.

Owns the session lifecycle: create, start, talk to, stop, finalize. Docker
transport lives in ``docker_client``, SQL in ``repository``, the SSE pipeline
in ``streaming``, and reaping in ``cleanup``.
"""

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import get_settings
from helprs.core.database import get_db_context
from helprs.core.exceptions import ConflictError, ExternalServiceError, NotFoundError
from helprs.modules.container import repository
from helprs.modules.container.docker_client import (
    CLAUDE_RUNNER_IMAGE,
    LABEL_BOOT_ID,
    LABEL_SESSION_ID,
    DockerClient,
)
from helprs.modules.container.models import ContainerSession, ContainerStatus, SessionEvent
from helprs.modules.container.pr_comment import build_session_url, extract_score_card, format_pr_comment
from helprs.modules.container.scorecard import extract_scorecard
from helprs.modules.installation import repository as installation_repository
from helprs.modules.installation.service import mint_installation_token, post_pr_comment_with_retry

logger = structlog.get_logger()

# Where skills live inside *this* process, used to validate the skill exists.
_LOCAL_SKILLS_PATH = Path(__file__).resolve().parents[5] / "skills"
_DOCKER_SKILLS_PATH = Path("/app/skills")
SKILLS_BASE_PATH = _DOCKER_SKILLS_PATH if _DOCKER_SKILLS_PATH.exists() else _LOCAL_SKILLS_PATH

# Docker-in-Docker: a bind mount source must be a path on the *host*, not one
# inside the API container.
SKILLS_HOST_PATH = os.environ.get("SKILLS_HOST_PATH", str(SKILLS_BASE_PATH))

SCORECARD_SKILL = "challenge-me"


# --- Session records -------------------------------------------------------


# Identity of this API process, stamped on every container it starts.
#
# Several uvicorn workers share one Docker socket, so "every running
# container" is not the same set as "the ones I started". Without this a
# worker's shutdown hook cancelled its peers' live sessions.
_boot_id: tuple[int, str] | None = None


def current_boot_id() -> str:
    """A value unique to this process and stable for its lifetime.

    Recomputed when the PID changes, so a forked worker never inherits its
    parent's id: uvicorn's ``--workers`` mode may fork after import, and two
    workers sharing a boot id would each stop the other's containers -- the
    exact bug this exists to prevent.
    """
    global _boot_id
    pid = os.getpid()
    if _boot_id is None or _boot_id[0] != pid:
        _boot_id = (pid, f"{pid}-{uuid4().hex[:8]}")
    return _boot_id[1]


async def create_session(
    db: AsyncSession,
    installation_id: UUID,
    pr_number: int,
    repo_full_name: str,
    skill_name: str,
    user_id: UUID | None = None,
) -> ContainerSession:
    """Record a session in PENDING state; no container exists yet."""
    session = await repository.add(
        db,
        ContainerSession(
            installation_id=installation_id,
            user_id=user_id,
            pr_number=pr_number,
            repo_full_name=repo_full_name,
            skill_name=skill_name,
            status=ContainerStatus.PENDING,
        ),
    )
    await logger.ainfo(
        "container_session_created",
        session_id=str(session.id),
        repo=repo_full_name,
        pr=pr_number,
        skill=skill_name,
    )
    return session


async def get_session(db: AsyncSession, session_id: UUID) -> ContainerSession | None:
    return await repository.get(db, session_id)


async def get_session_or_404(db: AsyncSession, session_id: UUID) -> ContainerSession:
    session = await repository.get(db, session_id)
    if session is None:
        raise NotFoundError("Container session not found")
    return session


async def get_session_events(db: AsyncSession, session_id: UUID) -> list[SessionEvent]:
    await get_session_or_404(db, session_id)
    return await repository.list_events(db, session_id)


async def delete_session(db: AsyncSession, session_id: UUID) -> None:
    await repository.delete(db, await get_session_or_404(db, session_id))


# --- Container lifecycle ---------------------------------------------------


def _resolve_skill_dir(skill_name: str, base: Path) -> Path:
    """Resolve a skill directory, refusing anything outside ``base``.

    The name reaches here from an API request and from the webhook path, which
    skips request-schema validation entirely — so the check belongs at the
    Docker boundary, where a traversal would become a host bind mount.
    """
    candidate = (base / skill_name).resolve()
    if not candidate.is_relative_to(base.resolve()) or not candidate.is_dir():
        raise NotFoundError(f"Skill '{skill_name}' not found")
    return candidate


async def start_container(
    db: AsyncSession,
    session_id: UUID,
    docker: DockerClient,
    claude_oauth_token: str,
    github_token: str,
    skills_base_path: Path | None = None,
) -> ContainerSession:
    """Provision the runner container and move the session PENDING -> RUNNING."""
    cs = await get_session_or_404(db, session_id)
    if cs.status != ContainerStatus.PENDING:
        raise ConflictError(f"Cannot start session in '{cs.status.value}' state")

    base = skills_base_path if skills_base_path is not None else SKILLS_BASE_PATH
    try:
        _resolve_skill_dir(cs.skill_name, base)
    except NotFoundError:
        # Committed, not flushed: the raise below unwinds through get_db,
        # which rolls back, so a flush here would be discarded along with the
        # status it just recorded. The caller commits the row before calling
        # this, so there is a row to update.
        cs.status = ContainerStatus.FAILED
        cs.completed_at = datetime.now(UTC)
        await db.commit()
        raise

    try:
        container_id = await docker.create_container(
            image=CLAUDE_RUNNER_IMAGE,
            environment={
                "CLAUDE_CODE_OAUTH_TOKEN": claude_oauth_token,
                "GITHUB_TOKEN": github_token,
                "SKILL_NAME": cs.skill_name,
                "PR_NUMBER": str(cs.pr_number),
                "REPO_FULL_NAME": cs.repo_full_name,
            },
            volumes=[f"{SKILLS_HOST_PATH}/{cs.skill_name}:/skills/{cs.skill_name}:ro"],
            labels={
                LABEL_SESSION_ID: str(cs.id),
                LABEL_BOOT_ID: current_boot_id(),
                "helprs.skill": cs.skill_name,
                "helprs.repo": cs.repo_full_name,
            },
        )
        await docker.start_container(container_id)
    except Exception as exc:
        cs.status = ContainerStatus.FAILED
        cs.completed_at = datetime.now(UTC)
        await db.commit()
        await logger.aerror("container_start_failed", session_id=str(session_id), error=str(exc))
        raise ExternalServiceError(f"Failed to start container: {exc}") from exc

    cs.container_id = container_id
    cs.status = ContainerStatus.RUNNING
    cs.started_at = datetime.now(UTC)
    await db.flush()

    await logger.ainfo("container_started", session_id=str(session_id), container_id=container_id)
    return cs


async def send_message(db: AsyncSession, session_id: UUID, docker: DockerClient, content: str) -> None:
    """Hand a user message to the running container's read loop."""
    cs = await get_session_or_404(db, session_id)
    if cs.status != ContainerStatus.RUNNING or not cs.container_id:
        raise ConflictError("Container is not running")

    try:
        await docker.write_to_container(cs.container_id, content)
    except Exception as exc:
        await logger.aerror("container_message_failed", session_id=str(session_id), error=str(exc))
        raise ExternalServiceError(f"Failed to send message to container: {exc}") from exc

    await logger.ainfo("container_message_sent", session_id=str(session_id))


async def stop_container(db: AsyncSession, session_id: UUID, docker: DockerClient) -> ContainerSession:
    """Abort a session at the user's request."""
    cs = await get_session_or_404(db, session_id)
    if cs.status not in repository.UNFINISHED_STATUSES:
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

    # Not COMPLETED: the skill never finished, and reporting an abort as a
    # success would corrupt every completion statistic.
    cs.status = ContainerStatus.CANCELLED
    cs.completed_at = datetime.now(UTC)
    await db.flush()

    await logger.ainfo("container_stopped", session_id=str(session_id))
    return cs


async def await_exit_status(docker: DockerClient, container_id: str, *, ttl_seconds: int) -> ContainerStatus:
    """Block until the container exits and map that to a session status.

    Takes no database session on purpose. This wait lasts as long as the skill
    runs -- up to the full TTL -- and holding a pooled connection, plus a lock
    on the session row, across it would starve the pool from a handful of
    abandoned sessions.
    """
    try:
        exit_code = await asyncio.wait_for(docker.wait_container(container_id), timeout=ttl_seconds)
        return ContainerStatus.COMPLETED if exit_code == 0 else ContainerStatus.FAILED
    except TimeoutError:
        await logger.awarning("container_timeout", container_id=container_id)
        return ContainerStatus.TIMEOUT


async def mark_completed(db: AsyncSession, session_id: UUID, status: ContainerStatus) -> ContainerSession:
    """Record a terminal status against a session. Write-only, no waiting."""
    cs = await get_session_or_404(db, session_id)
    if cs.status != ContainerStatus.RUNNING:
        return cs

    cs.status = status
    cs.completed_at = datetime.now(UTC)
    await db.flush()
    return cs


# --- Finalization ----------------------------------------------------------


async def finalize_session(session_id: UUID, docker: DockerClient) -> ContainerStatus:
    """Everything that must happen once a session's container exits.

    Deliberately independent of the HTTP request that started the stream: a
    browser closing its tab must not leave the session stuck RUNNING with its
    scorecard unextracted and its PR comment unposted.
    """
    settings = get_settings()
    try:
        # Three phases, so no database connection is held across the wait.
        async with get_db_context() as db:
            cs = await get_session_or_404(db, session_id)
            if cs.status != ContainerStatus.RUNNING or not cs.container_id:
                return cs.status
            container_id = cs.container_id

        status = await await_exit_status(docker, container_id, ttl_seconds=settings.CONTAINER_TTL_SECONDS)
        with contextlib.suppress(Exception):
            await docker.remove_container(container_id, force=True)

        async with get_db_context() as db:
            completed = await mark_completed(db, session_id, status)
            if status == ContainerStatus.COMPLETED:
                await _persist_scorecard(db, completed)
                await _post_results_comment(db, completed)
    except Exception:
        # The container's own outcome is known and already recorded by this
        # point in every path but an early one; reporting FAILED for a
        # bookkeeping error would tell the user their skill run failed when
        # it did not.
        await logger.aexception("session_finalization_failed", session_id=str(session_id))
        return ContainerStatus.FAILED

    return status


def _last_scorecard_in(events: list[SessionEvent]) -> dict | None:
    """Find the scorecard block in the most recent event that carries one.

    Assistant text blocks are checked first (that is where the skill writes
    it); the ``result`` event, which echoes the final text, is the fallback.
    """
    for event in reversed(events):
        message = event.data.get("message")
        if event.data.get("type") == "assistant" and isinstance(message, dict):
            for block in reversed(message.get("content", [])):
                if block.get("type") == "text":
                    scorecard = extract_scorecard(block.get("text", ""))
                    if scorecard:
                        return scorecard

    for event in reversed(events):
        if event.data.get("type") == "result" and isinstance(event.data.get("result"), str):
            scorecard = extract_scorecard(event.data["result"])
            if scorecard:
                return scorecard
    return None


async def _persist_scorecard(db: AsyncSession, cs: ContainerSession) -> None:
    """Store the skill's scorecard, if it emitted one."""
    scorecard = _last_scorecard_in(await repository.list_events(db, cs.id))
    if scorecard:
        cs.scorecard = scorecard
        await db.flush()


async def _post_results_comment(db: AsyncSession, cs: ContainerSession) -> None:
    """Post the score card back to the PR, when the install opted in.

    Best effort: a GitHub failure must not change the session's outcome. The
    token is minted fresh because a long session can outlive the one used to
    start it.
    """
    if cs.skill_name != SCORECARD_SKILL:
        return

    try:
        installation = await installation_repository.get_by_id(db, cs.installation_id)
        if not installation or not installation.post_results_to_pr:
            return

        score_card = await extract_score_card(cs.id, db)
        if not score_card:
            await logger.ainfo("post_results_no_score_card", session_id=str(cs.id))
            return

        settings = get_settings()
        comment_body = format_pr_comment(
            score_card,
            build_session_url(
                app_base_url=settings.APP_BASE_URL,
                installation_id=cs.installation_id,
                repo_full_name=cs.repo_full_name,
                pr_number=cs.pr_number,
            ),
        )
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
            session_id=str(cs.id),
            pr_number=cs.pr_number,
            repo=cs.repo_full_name,
        )
    except Exception:
        await logger.aexception("post_results_comment_failed", session_id=str(cs.id))
