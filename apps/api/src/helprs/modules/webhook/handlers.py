"""Webhook event handlers."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.installation.service import (
    create_installation,
    get_installation_by_github_id,
    mint_installation_token,
    post_pr_comment_with_retry,
    soft_delete_installation,
    suspend_installation,
    unsuspend_installation,
)

logger = structlog.get_logger()


def _extract_installation_id(payload: dict) -> int:
    """Extract installation ID from webhook payload, raising ValueError on missing fields."""
    try:
        return payload["installation"]["id"]
    except (KeyError, TypeError) as e:
        raise ValueError(f"Malformed webhook payload: missing installation.id ({e})") from e


async def handle_installation_created(payload: dict, session: AsyncSession) -> None:
    """Handle installation.created webhook event."""
    installation = await create_installation(session, payload)
    await logger.ainfo(
        "webhook_installation_created",
        installation_id=str(installation.id),
        github_installation_id=installation.github_installation_id,
    )


async def handle_installation_deleted(payload: dict, session: AsyncSession) -> None:
    """Handle installation.deleted webhook event."""
    github_id = _extract_installation_id(payload)
    result = await soft_delete_installation(session, github_id)
    if result:
        await logger.ainfo(
            "webhook_installation_deleted",
            github_installation_id=github_id,
        )
    else:
        await logger.awarning(
            "webhook_installation_delete_not_found",
            github_installation_id=github_id,
        )


async def handle_installation_suspended(payload: dict, session: AsyncSession) -> None:
    """Handle installation.suspended webhook event."""
    github_id = _extract_installation_id(payload)
    result = await suspend_installation(session, github_id)
    if result:
        await logger.ainfo(
            "webhook_installation_suspended",
            github_installation_id=github_id,
        )
    else:
        await logger.awarning(
            "webhook_installation_suspend_not_found",
            github_installation_id=github_id,
        )


async def handle_installation_unsuspended(payload: dict, session: AsyncSession) -> None:
    """Handle installation.unsuspended webhook event."""
    github_id = _extract_installation_id(payload)
    result = await unsuspend_installation(session, github_id)
    if result:
        await logger.ainfo(
            "webhook_installation_unsuspended",
            github_installation_id=github_id,
        )
    else:
        await logger.awarning(
            "webhook_installation_unsuspend_not_found",
            github_installation_id=github_id,
        )


async def handle_pull_request_opened(payload: dict, session: AsyncSession) -> None:
    """Handle pull_request.opened webhook event.

    Creates a container session with the default skill (challenge-me) and posts
    a PR comment with a link to the session.
    """
    from helprs.core.config import get_settings
    from helprs.modules.container.service import create_session

    github_id = _extract_installation_id(payload)
    installation = await get_installation_by_github_id(session, github_id)
    if installation is None:
        await logger.awarning(
            "webhook_pr_opened_installation_not_found",
            github_installation_id=github_id,
        )
        return

    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")
    repo = payload.get("repository") or {}
    repo_full_name = repo.get("full_name")

    if not pr_number or not repo_full_name:
        await logger.awarning(
            "webhook_pr_opened_missing_fields",
            has_pr_number=pr_number is not None,
            has_repo=repo_full_name is not None,
        )
        return

    cs = await create_session(
        db=session,
        installation_id=installation.id,
        pr_number=pr_number,
        repo_full_name=repo_full_name,
        skill_name="challenge-me",
    )

    settings = get_settings()
    owner, repo_name = repo_full_name.split("/", 1)

    try:
        token = await mint_installation_token(installation.github_installation_id, settings)
        comment_body = (
            f"**helPRs** session created for this PR.\n\n"
            f"Skill: `challenge-me` | "
            f"[Open session]({settings.APP_BASE_URL}/session/{installation.id}/{repo_full_name}/{pr_number})"
        )
        await post_pr_comment_with_retry(
            owner=owner,
            repo=repo_name,
            pr_number=pr_number,
            body=comment_body,
            installation_token=token,
        )
    except Exception:
        # PR comment is best-effort — never block session creation.
        await logger.aexception(
            "webhook_pr_comment_failed",
            session_id=str(cs.id),
        )

    await logger.ainfo(
        "webhook_pr_session_created",
        session_id=str(cs.id),
        repo=repo_full_name,
        pr=pr_number,
    )
