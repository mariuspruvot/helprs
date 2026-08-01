"""Unit tests for the webhook repository helpers."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from helprs.modules.webhook import repository
from helprs.modules.webhook.models import WebhookEvent
from helprs.modules.webhook.repository import DuplicateWebhookError


class TestCreateEvent:
    async def test_create_event_persists_pending_row(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="delivery-1",
            event_type="pull_request",
            action="opened",
            github_installation_id=42,
            payload={"hello": "world"},
        )

        assert event.id is not None
        assert event.status == "pending"
        assert event.retry_count == 0
        assert event.processed_at is None
        assert event.payload == {"hello": "world"}

        result = await db_session.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == "delivery-1"))
        row = result.scalar_one()
        assert row.id == event.id

    async def test_create_event_duplicate_delivery_id_raises(self, db_session):
        await repository.create_event(
            db_session,
            delivery_id="delivery-dup",
            event_type="pull_request",
            action="opened",
            github_installation_id=42,
            payload={},
        )

        with pytest.raises(DuplicateWebhookError):
            await repository.create_event(
                db_session,
                delivery_id="delivery-dup",
                event_type="pull_request",
                action="opened",
                github_installation_id=42,
                payload={},
            )

        result = await db_session.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == "delivery-dup"))
        rows = list(result.scalars().all())
        assert len(rows) == 1


class TestStatusTransitions:
    async def test_mark_processing(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-processing",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        claimed = await repository.mark_processing(db_session, event.id)
        assert claimed is True
        await db_session.refresh(event)
        assert event.status == "processing"

    async def test_mark_processing_returns_false_for_terminal_row(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-processing-terminal",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await repository.mark_processed(db_session, event.id)

        # Already-terminal rows cannot be re-claimed.
        claimed = await repository.mark_processing(db_session, event.id)
        assert claimed is False

    async def test_mark_processing_returns_false_for_fresh_processing_row(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-processing-fresh",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        first = await repository.mark_processing(db_session, event.id)
        assert first is True

        # A fresh `processing` row (updated_at within the stale window) cannot
        # be re-claimed by another worker.
        second = await repository.mark_processing(db_session, event.id)
        assert second is False

    async def test_mark_processed(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-processed",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await repository.mark_processed(db_session, event.id)
        await db_session.refresh(event)
        assert event.status == "processed"
        assert event.processed_at is not None

    async def test_mark_ignored(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-ignored",
            event_type="issues",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await repository.mark_ignored(db_session, event.id)
        await db_session.refresh(event)
        assert event.status == "ignored"
        assert event.processed_at is not None

    async def test_mark_failed_increments_retry_count(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-failed",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await repository.mark_failed(db_session, event.id, "boom")
        await db_session.refresh(event)
        assert event.status == "failed"
        assert event.error_message == "boom"
        assert event.retry_count == 1

        await repository.mark_failed(db_session, event.id, "boom again")
        await db_session.refresh(event)
        assert event.retry_count == 2

    async def test_mark_failed_transitions_to_abandoned_at_retry_cap(self, db_session):
        """P21: once retry_count reaches MAX_RETRY_COUNT the event is marked
        ``abandoned`` (permanent) instead of ``failed`` and a warning log is
        emitted for operator alerting."""
        import structlog

        event = await repository.create_event(
            db_session,
            delivery_id="d-abandoned",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        # Drive retry_count up to MAX - 1 via repeated mark_failed calls.
        for _ in range(repository.MAX_RETRY_COUNT - 1):
            await repository.mark_failed(db_session, event.id, "transient")

        await db_session.refresh(event)
        assert event.status == "failed"
        assert event.retry_count == repository.MAX_RETRY_COUNT - 1

        with structlog.testing.capture_logs() as logs:
            await repository.mark_failed(db_session, event.id, "final")

        await db_session.refresh(event)
        assert event.status == "abandoned"
        assert event.retry_count == repository.MAX_RETRY_COUNT
        assert event.error_message == "final"

        assert any(
            entry.get("event") == "webhook_event_abandoned" and entry.get("log_level") == "warning" for entry in logs
        ), f"expected webhook_event_abandoned warning, got {logs}"


class TestGetReplayableEvents:
    async def _backdate(self, db_session, event_id, seconds: int):
        """Age an event so the grace-period filter applies.

        Both timestamps: the filter measures idleness from ``updated_at`` so a
        retried event waits between attempts, while ordering still uses
        ``created_at``.
        """
        past = datetime.now(UTC) - timedelta(seconds=seconds)
        await db_session.execute(
            update(WebhookEvent).where(WebhookEvent.id == event_id).values(created_at=past, updated_at=past)
        )
        await db_session.commit()

    async def test_returns_old_pending_events(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-replay-pending",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await self._backdate(db_session, event.id, 60)

        events = await repository.get_replayable_events(db_session, older_than_seconds=30)
        assert any(e.id == event.id for e in events)

    async def test_failed_events_are_retried(self, db_session):
        """Regression: mark_failed wrote "failed" and this query only looked at
        "pending"/"processing", so nothing ever moved a failed row back. One
        handler exception dropped the delivery for good, retry_count could
        never pass 1, and the abandoned transition was unreachable."""
        event = await repository.create_event(
            db_session,
            delivery_id="d-replay-failed",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await repository.mark_failed(db_session, event.id, "handler blew up")
        await self._backdate(db_session, event.id, 60)

        events = await repository.get_replayable_events(db_session, older_than_seconds=30)
        assert any(e.id == event.id for e in events)

    async def test_a_failed_event_can_be_claimed_again(self, db_session):
        """Selecting it is not enough — mark_processing has to accept it too,
        or the reaper picks the same rows forever without progressing."""
        event = await repository.create_event(
            db_session,
            delivery_id="d-reclaim-failed",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await repository.mark_failed(db_session, event.id, "transient")
        await self._backdate(db_session, event.id, 60)

        assert await repository.mark_processing(db_session, event.id) is True

    async def test_abandoned_events_are_never_retried(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-abandoned-never-retried",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        for _ in range(repository.MAX_RETRY_COUNT):
            await repository.mark_failed(db_session, event.id, "still broken")
        await self._backdate(db_session, event.id, 60)

        await db_session.refresh(event)
        assert event.status == "abandoned"
        events = await repository.get_replayable_events(db_session, older_than_seconds=30)
        assert all(e.id != event.id for e in events)
        assert await repository.mark_processing(db_session, event.id) is False

    async def test_excludes_fresh_events(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-replay-fresh",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )

        events = await repository.get_replayable_events(db_session, older_than_seconds=30)
        assert all(e.id != event.id for e in events)

    async def test_excludes_processed_events(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-replay-processed",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await self._backdate(db_session, event.id, 60)
        await repository.mark_processed(db_session, event.id)

        events = await repository.get_replayable_events(db_session, older_than_seconds=30)
        assert all(e.id != event.id for e in events)

    async def test_excludes_events_with_retry_count_at_cap(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-replay-retrycap",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await self._backdate(db_session, event.id, 60)
        # Push retry_count to 5 (cap).
        await db_session.execute(update(WebhookEvent).where(WebhookEvent.id == event.id).values(retry_count=5))
        await db_session.commit()

        events = await repository.get_replayable_events(db_session, older_than_seconds=30)
        assert all(e.id != event.id for e in events)

    async def test_returns_processing_events(self, db_session):
        event = await repository.create_event(
            db_session,
            delivery_id="d-replay-processing",
            event_type="pull_request",
            action="opened",
            github_installation_id=1,
            payload={},
        )
        await repository.mark_processing(db_session, event.id)
        await self._backdate(db_session, event.id, 60)

        events = await repository.get_replayable_events(db_session, older_than_seconds=30)
        assert any(e.id == event.id for e in events)
