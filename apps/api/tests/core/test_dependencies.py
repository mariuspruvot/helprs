"""Tests for get_current_user dependency."""

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from helprs.core.config import get_settings
from helprs.core.dependencies import get_current_user
from helprs.core.exceptions import UnauthorizedError
from helprs.core.security import create_access_token


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


class TestGetCurrentUser:
    async def test_missing_auth_header(self, settings):
        request = MagicMock()
        request.headers = {}
        request.query_params = {}
        session = AsyncMock()

        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            await get_current_user(request, session, settings)

    async def test_invalid_bearer_format(self, settings):
        request = MagicMock()
        request.headers = {"Authorization": "Basic abc123"}
        request.query_params = {}
        session = AsyncMock()

        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            await get_current_user(request, session, settings)

    async def test_invalid_jwt(self, settings):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer invalid_token"}
        request.query_params = {}
        session = AsyncMock()

        with pytest.raises(UnauthorizedError, match="Invalid or expired"):
            await get_current_user(request, session, settings)

    async def test_expired_jwt(self, settings):
        token = create_access_token(
            {"sub": str(uuid.uuid4()), "github_login": "test"},
            settings.SECRET_KEY,
            timedelta(seconds=-1),
        )
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        request.query_params = {}
        session = AsyncMock()

        with pytest.raises(UnauthorizedError, match="Invalid or expired"):
            await get_current_user(request, session, settings)

    async def test_user_not_found(self, settings):
        user_id = uuid.uuid4()
        token = create_access_token(
            {"sub": str(user_id), "github_login": "ghost"},
            settings.SECRET_KEY,
        )
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        request.query_params = {}

        # Mock session that returns no user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute.return_value = mock_result

        with pytest.raises(UnauthorizedError, match="User not found"):
            await get_current_user(request, session, settings)

    async def test_valid_token_returns_user(self, settings):
        user_id = uuid.uuid4()
        token = create_access_token(
            {"sub": str(user_id), "github_login": "validuser"},
            settings.SECRET_KEY,
        )
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        request.query_params = {}

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.github_login = "validuser"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        session = AsyncMock()
        session.execute.return_value = mock_result

        user = await get_current_user(request, session, settings)
        assert user.github_login == "validuser"

    async def test_query_param_fallback_when_no_header(self, settings):
        """SSE clients (EventSource) cannot send headers — token comes via ?access_token=."""
        user_id = uuid.uuid4()
        token = create_access_token(
            {"sub": str(user_id), "github_login": "ssouser"},
            settings.SECRET_KEY,
        )
        request = MagicMock()
        request.headers = {}  # no Authorization header
        request.query_params = {"access_token": token}

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.github_login = "ssouser"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        session = AsyncMock()
        session.execute.return_value = mock_result

        user = await get_current_user(request, session, settings)
        assert user.github_login == "ssouser"

    async def test_header_takes_precedence_over_query_param(self, settings):
        """If both header and query param are present, the header wins."""
        user_id = uuid.uuid4()
        header_token = create_access_token(
            {"sub": str(user_id), "github_login": "headeruser"},
            settings.SECRET_KEY,
        )
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {header_token}"}
        request.query_params = {"access_token": "garbage-should-be-ignored"}

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.github_login = "headeruser"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        session = AsyncMock()
        session.execute.return_value = mock_result

        user = await get_current_user(request, session, settings)
        assert user.github_login == "headeruser"
