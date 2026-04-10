"""Tests for startup crash-replay of webhook events."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.database import Base
from helprs.modules.webhook import repository
from helprs.modules.webhook.models import WebhookEvent
from helprs.modules.webhook.tasks import process_webhook_event

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


@pytest.fixture
async def replay_session_factory():
    """A real session_factory so background tasks can open their own session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _backdate(factory, event_id, seconds: int) -> None:
    async with factory() as s:
        past = datetime.now(UTC) - timedelta(seconds=seconds)
        await s.execute(update(WebhookEvent).where(WebhookEvent.id == event_id).values(created_at=past))
        await s.commit()


class TestReplay:
    async def test_replay_processes_stale_pending_event(self, replay_session_factory):
        async with replay_session_factory() as s:
            event = await repository.create_event(
                s,
                delivery_id="replay-opened",
                event_type="pull_request",
                action="opened",
                github_installation_id=12345678,
                payload={
                    "action": "opened",
                    "installation": {"id": 12345678},
                    "pull_request": {"number": 1},
                    "repository": {"full_name": "a/b"},
                },
            )
            event_id = event.id

        await _backdate(replay_session_factory, event_id, 60)

        # Exercise the same function the lifespan would call.
        await process_webhook_event(replay_session_factory, event_id)

        async with replay_session_factory() as s:
            row = await s.get(WebhookEvent, event_id)
        assert row.status == "processed"
        assert row.processed_at is not None

    async def test_replay_marks_unhandled_event_as_ignored(self, replay_session_factory):
        async with replay_session_factory() as s:
            event = await repository.create_event(
                s,
                delivery_id="replay-unhandled",
                event_type="issues",
                action="opened",
                github_installation_id=None,
                payload={},
            )
            event_id = event.id

        await _backdate(replay_session_factory, event_id, 60)
        await process_webhook_event(replay_session_factory, event_id)

        async with replay_session_factory() as s:
            row = await s.get(WebhookEvent, event_id)
        assert row.status == "ignored"

    async def test_get_replayable_events_excludes_max_retry(self, replay_session_factory):
        async with replay_session_factory() as s:
            event = await repository.create_event(
                s,
                delivery_id="replay-maxretry",
                event_type="pull_request",
                action="opened",
                github_installation_id=1,
                payload={},
            )
            event_id = event.id

        await _backdate(replay_session_factory, event_id, 60)

        async with replay_session_factory() as s:
            await s.execute(update(WebhookEvent).where(WebhookEvent.id == event_id).values(retry_count=5))
            await s.commit()

            events = await repository.get_replayable_events(s, older_than_seconds=30)
        assert all(e.id != event_id for e in events)
