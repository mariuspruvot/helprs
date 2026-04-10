"""Background-task workers for the webhook module.

Runs the dispatcher off the request path so the HTTP handler can return 200
quickly. Each invocation opens its own ``AsyncSession`` — background tasks
run after the request context has exited and the request session is closed.

Invariant: ``process_webhook_event`` must NEVER let an exception propagate
past the task boundary. The triggering HTTP request has already returned
200 and FastAPI has no way to surface a background-task failure to the
client. Any failure must be logged and (best-effort) recorded on the
``WebhookEvent`` row.
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from helprs.modules.webhook import repository
from helprs.modules.webhook.dispatcher import dispatch_webhook
from helprs.modules.webhook.models import WebhookEvent

logger = structlog.get_logger()

_TASK_CONTEXT_KEYS = (
    "webhook_event_id",
    "delivery_id",
    "event_type",
    "action",
    "github_installation_id",
)


async def _record_failure(
    session_factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
    error_message: str,
) -> None:
    """Best-effort ``mark_failed`` using a fresh session.

    The primary session may be in a broken state after the handler raised.
    This helper catches any secondary DB failure so the outer task can
    still return cleanly.
    """
    try:
        async with session_factory() as failure_session:
            await repository.mark_failed(failure_session, event_id, error_message)
    except Exception:
        await logger.aexception("webhook_event_mark_failed_errored", event_id=str(event_id))


async def process_webhook_event(
    session_factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
) -> None:
    """Process a persisted ``WebhookEvent`` by id.

    Atomically claims the row via ``mark_processing``; if another worker has
    already claimed it (multi-replica, startup replay + reaper overlap, or
    redelivery race), this call returns cleanly without dispatching.

    On success the row transitions to ``processed`` / ``ignored``; on
    handler exception the row transitions to ``failed`` (or ``abandoned``
    once the retry cap is hit) via ``_record_failure``. Any unexpected
    exception during the claim / transition flow is also caught in the
    outer guard so the task boundary is never breached (AC #7).
    """
    # Background tasks do NOT share the request-scoped structlog context —
    # bind what we know now and rebind the rest once the row is loaded.
    structlog.contextvars.bind_contextvars(webhook_event_id=str(event_id))
    try:
        async with session_factory() as session:
            event: WebhookEvent | None = await session.get(WebhookEvent, event_id)
            if event is None:
                await logger.awarning("webhook_event_not_found", event_id=str(event_id))
                return

            structlog.contextvars.bind_contextvars(
                delivery_id=event.delivery_id,
                event_type=event.event_type,
                action=event.action,
                github_installation_id=event.github_installation_id,
            )

            claimed = await repository.mark_processing(session, event.id)
            if not claimed:
                await logger.ainfo("webhook_event_already_claimed")
                return

            try:
                result = await dispatch_webhook(
                    event.event_type,
                    event.action or "",
                    event.payload,
                    session,
                )
            except Exception as exc:
                await logger.aexception("webhook_background_task_failed")
                await _record_failure(session_factory, event.id, str(exc))
                return

            if result.handled:
                await repository.mark_processed(session, event.id)
            else:
                await repository.mark_ignored(session, event.id)
    except Exception as exc:
        # Outermost guard: covers failures in session.get / mark_processing /
        # mark_processed / mark_ignored — anything outside the inner dispatcher
        # try/except. AC #7 requires that exceptions never escape the task.
        await logger.aexception("webhook_event_processing_errored")
        await _record_failure(session_factory, event_id, f"process_webhook_event: {exc}")
    finally:
        # Unbind only the keys this task bound so unrelated request-scoped
        # context (e.g. ``request_id``) is not wiped.
        structlog.contextvars.unbind_contextvars(*_TASK_CONTEXT_KEYS)
