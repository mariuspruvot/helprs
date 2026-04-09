"""Unit tests for identity service."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from helprs.core.exceptions import ExternalServiceError, UnauthorizedError
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.modules.identity.service import (
    create_token_pair,
    exchange_code_for_token,
    fetch_github_user,
    get_decrypted_github_token,
    get_or_create_user,
    refresh_tokens,
)


class TestExchangeCodeForToken:
    async def test_success(self, settings):
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "gho_abc123", "token_type": "bearer"}
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.identity.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await exchange_code_for_token("test_code", settings)
            assert result["access_token"] == "gho_abc123"

    async def test_github_returns_error(self, settings):
        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "bad_verification_code"}
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.identity.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(UnauthorizedError, match="bad_verification_code"):
                await exchange_code_for_token("bad_code", settings)

    async def test_timeout(self, settings):
        with patch("helprs.modules.identity.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ExternalServiceError, match="temporarily unavailable"):
                await exchange_code_for_token("code", settings)

    async def test_http_error(self, settings):
        with patch("helprs.modules.identity.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_resp
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ExternalServiceError):
                await exchange_code_for_token("code", settings)


class TestFetchGithubUser:
    async def test_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 123, "login": "octocat"}
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.identity.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_github_user("gho_token")
            assert result["login"] == "octocat"

    async def test_401_raises_unauthorized(self):
        with patch("helprs.modules.identity.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_client.get.side_effect = httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=mock_resp
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(UnauthorizedError, match="invalid or revoked"):
                await fetch_github_user("bad_token")

    async def test_timeout_raises_external_service_error(self):
        with patch("helprs.modules.identity.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ExternalServiceError, match="temporarily unavailable"):
                await fetch_github_user("gho_token")

    async def test_5xx_raises_external_service_error(self):
        with patch("helprs.modules.identity.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_client.get.side_effect = httpx.HTTPStatusError(
                "Service Unavailable", request=MagicMock(), response=mock_resp
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ExternalServiceError, match="GitHub API error"):
                await fetch_github_user("gho_token")


class TestGetOrCreateUser:
    async def test_creates_new_user(self, db_session, settings):
        github_data = {
            "id": 99999999,
            "login": "newuser",
            "email": "new@example.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/99999999",
        }
        user = await get_or_create_user(db_session, github_data, "gho_new_token", settings)
        assert user.github_id == 99999999
        assert user.github_login == "newuser"
        assert user.email == "new@example.com"

    async def test_updates_existing_user(self, db_session, settings, test_user):
        existing_user, _ = test_user
        github_data = {
            "id": existing_user.github_id,
            "login": "updated_login",
            "email": "updated@example.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
        }
        user = await get_or_create_user(db_session, github_data, "gho_updated_token", settings)
        assert user.id == existing_user.id
        assert user.github_login == "updated_login"
        assert user.email == "updated@example.com"


class TestCreateTokenPair:
    def test_returns_two_tokens(self, settings):
        user = MagicMock()
        user.id = "550e8400-e29b-41d4-a716-446655440000"
        user.github_login = "testuser"

        access, refresh = create_token_pair(user, settings)
        assert isinstance(access, str)
        assert isinstance(refresh, str)
        assert access != refresh


class TestRefreshTokens:
    async def test_valid_refresh(self, db_session, settings, test_user):
        user, _ = test_user
        refresh_token = create_access_token(
            {"sub": str(user.id), "type": "refresh"},
            settings.SECRET_KEY,
            timedelta(days=7),
        )
        new_access, new_refresh = await refresh_tokens(refresh_token, db_session, settings)
        assert isinstance(new_access, str)
        assert isinstance(new_refresh, str)

    async def test_invalid_refresh_token(self, db_session, settings):
        with pytest.raises(UnauthorizedError, match="Invalid or expired"):
            await refresh_tokens("invalid_token", db_session, settings)

    async def test_non_refresh_token_rejected(self, db_session, settings, test_user):
        _, access_token = test_user  # This is an access token, not refresh
        with pytest.raises(UnauthorizedError, match="not a refresh token"):
            await refresh_tokens(access_token, db_session, settings)

    async def test_user_not_found(self, db_session, settings):
        import uuid

        refresh_token = create_access_token(
            {"sub": str(uuid.uuid4()), "type": "refresh"},
            settings.SECRET_KEY,
            timedelta(days=7),
        )
        with pytest.raises(UnauthorizedError, match="User not found"):
            await refresh_tokens(refresh_token, db_session, settings)


class TestGetDecryptedGithubToken:
    def test_valid_token(self, settings):
        user = MagicMock()
        user.github_access_token_enc = fernet_encrypt("gho_test", settings.FERNET_KEY)
        result = get_decrypted_github_token(user, settings.FERNET_KEY)
        assert result == "gho_test"

    def test_corrupted_token(self, settings):
        user = MagicMock()
        user.github_access_token_enc = "corrupted_data"
        with pytest.raises(UnauthorizedError, match="corrupted"):
            get_decrypted_github_token(user, settings.FERNET_KEY)
