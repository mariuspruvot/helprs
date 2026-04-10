"""Tests for webhook event dispatcher."""

from unittest.mock import AsyncMock, patch

import structlog

from helprs.modules.webhook import dispatcher
from helprs.modules.webhook.dispatcher import DispatchResult


class TestDispatchWebhook:
    async def test_installation_created_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("installation", "created"): mock_handler}):
            result = await dispatcher.dispatch_webhook("installation", "created", {"test": True}, db_session)
        mock_handler.assert_called_once_with({"test": True}, db_session)
        assert result.handled is True

    async def test_installation_deleted_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("installation", "deleted"): mock_handler}):
            result = await dispatcher.dispatch_webhook("installation", "deleted", {"test": True}, db_session)
        mock_handler.assert_called_once_with({"test": True}, db_session)
        assert result.handled is True

    async def test_installation_suspended_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("installation", "suspended"): mock_handler}):
            result = await dispatcher.dispatch_webhook("installation", "suspended", {"test": True}, db_session)
        mock_handler.assert_called_once_with({"test": True}, db_session)
        assert result.handled is True

    async def test_installation_unsuspended_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("installation", "unsuspended"): mock_handler}):
            result = await dispatcher.dispatch_webhook("installation", "unsuspended", {"test": True}, db_session)
        mock_handler.assert_called_once_with({"test": True}, db_session)
        assert result.handled is True

    async def test_pull_request_opened_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("pull_request", "opened"): mock_handler}):
            result = await dispatcher.dispatch_webhook("pull_request", "opened", {"x": 1}, db_session)
        mock_handler.assert_called_once_with({"x": 1}, db_session)
        assert result == DispatchResult.handled_result()

    async def test_pull_request_synchronize_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("pull_request", "synchronize"): mock_handler}):
            result = await dispatcher.dispatch_webhook("pull_request", "synchronize", {"x": 2}, db_session)
        mock_handler.assert_called_once_with({"x": 2}, db_session)
        assert result.handled is True

    async def test_issues_opened_is_ignored_and_logged(self, db_session):
        with structlog.testing.capture_logs() as logs:
            result = await dispatcher.dispatch_webhook("issues", "opened", {}, db_session)

        assert result.handled is False
        assert result == DispatchResult.ignored_result()
        assert any(entry.get("event") == "webhook_event_unhandled" for entry in logs)

    async def test_pull_request_closed_is_ignored(self, db_session):
        with structlog.testing.capture_logs() as logs:
            result = await dispatcher.dispatch_webhook("pull_request", "closed", {}, db_session)

        assert result.handled is False
        assert any(
            entry.get("event") == "webhook_event_unhandled" and entry.get("action") == "closed" for entry in logs
        )

    async def test_unknown_event_does_not_raise(self, db_session):
        # Regression — keep historic behavior that unknown events never raise.
        result = await dispatcher.dispatch_webhook("unknown_event", "unknown_action", {}, db_session)
        assert result.handled is False
