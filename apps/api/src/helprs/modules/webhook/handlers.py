"""Webhook event handlers."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.installation.service import (
    create_installation,
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
