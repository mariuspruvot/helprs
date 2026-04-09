"""Webhook event dispatcher."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.webhook.handlers import (
    handle_installation_created,
    handle_installation_deleted,
    handle_installation_suspended,
    handle_installation_unsuspended,
)

logger = structlog.get_logger()

# Map of (event_type, action) -> handler function
_HANDLERS: dict[tuple[str, str], object] = {
    ("installation", "created"): handle_installation_created,
    ("installation", "deleted"): handle_installation_deleted,
    ("installation", "suspended"): handle_installation_suspended,
    ("installation", "unsuspended"): handle_installation_unsuspended,
}


async def dispatch_webhook(event_type: str, action: str, payload: dict, session: AsyncSession) -> None:
    """Route webhook events to the appropriate handler."""
    handler = _HANDLERS.get((event_type, action))
    if handler:
        await handler(payload, session)
    else:
        await logger.ainfo(
            "webhook_event_unhandled",
            event_type=event_type,
            action=action,
        )
