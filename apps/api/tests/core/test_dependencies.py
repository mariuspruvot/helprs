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
        session = AsyncMock()

        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            await get_current_user(request, session, settings)

    async def test_invalid_bearer_format(self, settings):
        request = MagicMock()
        request.headers = {"Authorization": "Basic abc123"}
        session = AsyncMock()

        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            await get_current_user(request, session, settings)

    async def test_invalid_jwt(self, settings):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer invalid_token"}
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

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.github_login = "validuser"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        session = AsyncMock()
        session.execute.return_value = mock_result

        user = await get_current_user(request, session, settings)
        assert user.github_login == "validuser"
