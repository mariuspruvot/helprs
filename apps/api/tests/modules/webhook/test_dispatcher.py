"""Tests for webhook event dispatcher."""

from unittest.mock import AsyncMock, patch

from helprs.modules.webhook import dispatcher


class TestDispatchWebhook:
    async def test_installation_created_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("installation", "created"): mock_handler}):
            await dispatcher.dispatch_webhook("installation", "created", {"test": True}, db_session)
            mock_handler.assert_called_once_with({"test": True}, db_session)

    async def test_installation_deleted_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("installation", "deleted"): mock_handler}):
            await dispatcher.dispatch_webhook("installation", "deleted", {"test": True}, db_session)
            mock_handler.assert_called_once_with({"test": True}, db_session)

    async def test_installation_suspend_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("installation", "suspend"): mock_handler}):
            await dispatcher.dispatch_webhook("installation", "suspend", {"test": True}, db_session)
            mock_handler.assert_called_once_with({"test": True}, db_session)

    async def test_installation_unsuspend_routes_to_handler(self, db_session):
        mock_handler = AsyncMock()
        with patch.dict(dispatcher._HANDLERS, {("installation", "unsuspend"): mock_handler}):
            await dispatcher.dispatch_webhook("installation", "unsuspend", {"test": True}, db_session)
            mock_handler.assert_called_once_with({"test": True}, db_session)

    async def test_unknown_event_logs_gracefully(self, db_session):
        # Should not raise
        await dispatcher.dispatch_webhook("unknown_event", "unknown_action", {}, db_session)
