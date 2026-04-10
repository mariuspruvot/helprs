"""Smoke tests for pull_request placeholder handlers."""

import structlog

from helprs.modules.webhook import handlers
from tests.modules.webhook.conftest import make_pull_request_payload


class TestPullRequestHandlers:
    async def test_handle_opened_logs_event(self, db_session):
        payload = make_pull_request_payload("opened")
        with structlog.testing.capture_logs() as logs:
            await handlers.handle_pull_request_opened(payload, db_session)

        assert any(
            entry.get("event") == "pull_request_event_received"
            and entry.get("action") == "opened"
            and entry.get("pr_number") == 42
            and entry.get("repo") == "acme/repo"
            for entry in logs
        )

    async def test_handle_synchronize_logs_event(self, db_session):
        payload = make_pull_request_payload("synchronize")
        with structlog.testing.capture_logs() as logs:
            await handlers.handle_pull_request_synchronize(payload, db_session)

        assert any(
            entry.get("event") == "pull_request_event_received" and entry.get("action") == "synchronize"
            for entry in logs
        )

    async def test_malformed_payload_logs_warning_and_does_not_raise(self, db_session):
        # Missing installation.id — handler must swallow and log, never raise.
        payload = {"pull_request": {"number": 1}, "repository": {"full_name": "a/b"}}
        with structlog.testing.capture_logs() as logs:
            await handlers.handle_pull_request_opened(payload, db_session)

        assert any(
            entry.get("event") == "pull_request_event_malformed_payload" and entry.get("log_level") == "warning"
            for entry in logs
        )

    async def test_malformed_payload_does_not_touch_db(self, db_session):
        """Empty payload must produce a warning log and leave the DB untouched.

        Regression for the original test which had no assertion and passed
        iff the handler merely returned without raising.
        """
        from sqlalchemy import func, select

        from helprs.modules.webhook.models import WebhookEvent

        before_count = (await db_session.execute(select(func.count()).select_from(WebhookEvent))).scalar_one()

        payload = {}
        with structlog.testing.capture_logs() as logs:
            await handlers.handle_pull_request_opened(payload, db_session)

        # Handler must have logged the malformed warning, not raised.
        assert any(
            entry.get("event") == "pull_request_event_malformed_payload" and entry.get("log_level") == "warning"
            for entry in logs
        )

        # No DB writes from placeholder handlers, even on malformed input.
        after_count = (await db_session.execute(select(func.count()).select_from(WebhookEvent))).scalar_one()
        assert after_count == before_count
