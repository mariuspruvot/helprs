"""Webhook event dispatcher.

Routes ``(event_type, action)`` tuples to their handlers and reports back
whether a handler actually ran so the caller can transition the persisted
``WebhookEvent`` row to ``processed`` or ``ignored`` accordingly.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.webhook.handlers import (
    handle_installation_created,
    handle_installation_deleted,
    handle_installation_suspended,
    handle_installation_unsuspended,
)

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Outcome of dispatching a webhook event to a handler."""

    handled: bool

    @classmethod
    def handled_result(cls) -> "DispatchResult":
        return cls(handled=True)

    @classmethod
    def ignored_result(cls) -> "DispatchResult":
        return cls(handled=False)


WebhookHandler = Callable[[dict, AsyncSession], Awaitable[None]]

# Map of (event_type, action) -> handler function
_HANDLERS: dict[tuple[str, str], WebhookHandler] = {
    ("installation", "created"): handle_installation_created,
    ("installation", "deleted"): handle_installation_deleted,
    ("installation", "suspended"): handle_installation_suspended,
    ("installation", "unsuspended"): handle_installation_unsuspended,
}


async def dispatch_webhook(
    event_type: str,
    action: str,
    payload: dict,
    session: AsyncSession,
) -> DispatchResult:
    """Route a webhook event to its handler.

    Returns a ``DispatchResult`` indicating whether a handler ran. The caller
    uses this to transition the persisted ``WebhookEvent`` row to ``processed``
    (handled) or ``ignored`` (no handler registered).
    """
    handler = _HANDLERS.get((event_type, action))
    if handler:
        await handler(payload, session)
        return DispatchResult.handled_result()

    await logger.ainfo(
        "webhook_event_unhandled",
        event_type=event_type,
        action=action,
    )
    return DispatchResult.ignored_result()
