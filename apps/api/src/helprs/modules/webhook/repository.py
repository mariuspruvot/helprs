"""Persistence helpers for ``WebhookEvent``.

These are module-level async functions (no repository class) — kept flat to
match the inbound-adapter layout of the webhook module. Each helper commits
explicitly so status transitions are visible across tasks and survive crashes.

Concurrency model (Story 2.1 post-review)
------------------------------------------
- ``mark_processing`` is an atomic compare-and-swap: it only transitions a row
  to ``processing`` if the row is currently ``pending`` **or** a stale
  ``processing`` (``updated_at`` older than ``stale_after_seconds``). Returns
  ``True`` if the current worker won the claim, ``False`` otherwise. This is
  what makes the background-task + startup-replay + periodic-reaper paths safe
  across replicas / concurrent invocations.
- ``get_replayable_events`` uses DB-side ``now()`` for the cutoff comparison
  (no Python-vs-DB clock-skew hole) and caps the result set via ``limit`` so
  no startup-replay fan-out can exhaust the connection pool after a large
  backlog.
- ``mark_failed`` transitions to ``abandoned`` once ``retry_count`` reaches
  the cap (5) and emits a warning log, so operators can grep/alert instead of
  discovering dead events by accident.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.webhook.models import WebhookEvent

logger = structlog.get_logger()

MAX_RETRY_COUNT = 5
DEFAULT_REPLAY_LIMIT = 200
DEFAULT_STALE_AFTER_SECONDS = 60

# Unique-constraint name produced by Alembic for `delivery_id`. Used to scope
# the `IntegrityError` catch so non-delivery-id violations are never swallowed
# as "duplicate webhook".
_DELIVERY_ID_UNIQUE_INDEX = "ix_webhook_events_delivery_id"


class DuplicateWebhookError(Exception):
    """Raised when a WebhookEvent with the same delivery_id already exists.

    Intentionally a plain ``Exception`` (not a ``DomainError``) so it is never
    surfaced to HTTP clients — the router swallows it and still returns 200.
    """


def _is_delivery_id_conflict(exc: IntegrityError) -> bool:
    """True iff the IntegrityError was caused by the delivery_id unique index.

    We intentionally avoid re-raising any other IntegrityError as a duplicate
    webhook — e.g., a future NOT NULL / FK / CHECK violation should surface
    as a real 500, not be silently swallowed.
    """
    orig = getattr(exc, "orig", None)
    message = str(orig) if orig is not None else str(exc)
    return _DELIVERY_ID_UNIQUE_INDEX in message or "delivery_id" in message


async def create_event(
    session: AsyncSession,
    *,
    delivery_id: str,
    event_type: str,
    action: str | None,
    github_installation_id: int | None,
    payload: dict,
) -> WebhookEvent:
    """Insert a new pending WebhookEvent row.

    Raises ``DuplicateWebhookError`` if ``delivery_id`` is already present
    (GitHub redelivery — AC #4). Any other ``IntegrityError`` is re-raised
    unchanged so real constraint violations are not silently dropped.
    """
    event = WebhookEvent(
        delivery_id=delivery_id,
        event_type=event_type,
        action=action,
        github_installation_id=github_installation_id,
        payload=payload,
        status="pending",
    )
    session.add(event)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if _is_delivery_id_conflict(e):
            raise DuplicateWebhookError(delivery_id) from e
        raise
    await session.refresh(event)
    return event


async def mark_processing(
    session: AsyncSession,
    event_id: UUID,
    *,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> bool:
    """Atomically claim a webhook event for processing.

    Returns ``True`` if the current worker won the claim, ``False`` otherwise
    (row is terminal, does not exist, or another worker is actively
    processing it within the stale-window).

    Uses a conditional UPDATE with DB-side time so it is safe across
    replicas and clock skew::

        UPDATE webhook_events
           SET status='processing', updated_at = now()
         WHERE id = :id
           AND (status = 'pending'
                OR (status = 'processing'
                    AND updated_at < now() - interval ':stale_after s'))

    The ``interval`` value is bound as a parameter to avoid SQL injection.
    """
    stale_cutoff = func.now() - timedelta(seconds=stale_after_seconds)
    stmt = (
        update(WebhookEvent)
        .where(
            WebhookEvent.id == event_id,
            or_(
                WebhookEvent.status == "pending",
                and_(
                    WebhookEvent.status == "processing",
                    WebhookEvent.updated_at < stale_cutoff,
                ),
            ),
        )
        .values(status="processing", updated_at=func.now())
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    await session.commit()
    return (result.rowcount or 0) == 1


async def mark_processed(session: AsyncSession, event_id: UUID) -> None:
    """Transition a webhook event to ``processed`` (terminal, success)."""
    event = await session.get(WebhookEvent, event_id)
    if event is None:
        return
    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    await session.commit()


async def mark_ignored(session: AsyncSession, event_id: UUID) -> None:
    """Transition a webhook event to ``ignored`` (unhandled event type)."""
    event = await session.get(WebhookEvent, event_id)
    if event is None:
        return
    event.status = "ignored"
    event.processed_at = datetime.now(UTC)
    await session.commit()


async def mark_failed(session: AsyncSession, event_id: UUID, error_message: str) -> None:
    """Transition a webhook event to ``failed`` and increment retry_count.

    Once ``retry_count`` reaches ``MAX_RETRY_COUNT`` the event is transitioned
    to ``abandoned`` (terminal, permanent) and a warning log is emitted so
    operators can grep the stream and alert on cap-hit events instead of
    finding stuck rows by accident.
    """
    event = await session.get(WebhookEvent, event_id)
    if event is None:
        return
    new_retry_count = event.retry_count + 1
    event.retry_count = new_retry_count
    event.error_message = error_message
    if new_retry_count >= MAX_RETRY_COUNT:
        event.status = "abandoned"
        await logger.awarning(
            "webhook_event_abandoned",
            webhook_event_id=str(event_id),
            retry_count=new_retry_count,
            error_message=error_message,
        )
    else:
        event.status = "failed"
    await session.commit()


async def get_replayable_events(
    session: AsyncSession,
    *,
    older_than_seconds: int = 30,
    limit: int = DEFAULT_REPLAY_LIMIT,
) -> list[WebhookEvent]:
    """Return events eligible for crash-replay / periodic reaping.

    Selects rows still in ``pending`` or ``processing`` older than the grace
    period, with ``retry_count < MAX_RETRY_COUNT`` to skip permanently
    abandoned payloads. The cutoff uses DB-side ``now()`` to avoid
    Python-vs-DB clock-skew blackholes.

    The query is capped by ``limit`` (default ``200``) so a backlog after an
    outage cannot fan out to tens of thousands of concurrent tasks on the
    next boot — the reaper will drain whatever remains on the next cycle.
    """
    grace_cutoff = func.now() - timedelta(seconds=older_than_seconds)
    stmt = (
        select(WebhookEvent)
        .where(
            WebhookEvent.status.in_(("pending", "processing")),
            WebhookEvent.created_at < grace_cutoff,
            WebhookEvent.retry_count < MAX_RETRY_COUNT,
        )
        .order_by(WebhookEvent.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
