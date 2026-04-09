"""Unit tests for installation service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select

from helprs.core.exceptions import ExternalServiceError, ForbiddenError, UnauthorizedError
from helprs.modules.installation.models import Installation
from helprs.modules.installation.service import (
    create_installation,
    get_installation_access_token,
    get_installation_by_github_id,
    soft_delete_installation,
    verify_admin_permission,
)

SAMPLE_WEBHOOK_PAYLOAD = {
    "action": "created",
    "installation": {
        "id": 12345678,
        "account": {"login": "myorg", "id": 99999, "type": "Organization"},
        "repository_selection": "selected",
        "app_slug": "helprs",
        "target_type": "Organization",
        "permissions": {"pull_requests": "read", "contents": "read"},
        "events": ["pull_request"],
        "suspended_at": None,
    },
    "sender": {"login": "admin-user", "id": 111},
}


class TestCreateInstallation:
    async def test_creates_from_webhook_payload(self, db_session):
        installation = await create_installation(db_session, SAMPLE_WEBHOOK_PAYLOAD)

        assert installation.github_installation_id == 12345678
        assert installation.account_login == "myorg"
        assert installation.account_id == 99999
        assert installation.account_type == "Organization"
        assert installation.repository_selection == "selected"
        assert installation.app_slug == "helprs"
        assert installation.target_type == "Organization"
        assert installation.permissions == {"pull_requests": "read", "contents": "read"}
        assert installation.events == ["pull_request"]
        assert installation.deleted_at is None


class TestSoftDeleteInstallation:
    async def test_sets_deleted_at(self, db_session, test_installation):
        result = await soft_delete_installation(
            db_session, test_installation.github_installation_id
        )

        assert result is not None
        assert result.deleted_at is not None
        assert result.id == test_installation.id

        # Verify the record still exists (not hard deleted)
        stmt = select(Installation).where(Installation.id == test_installation.id)
        db_result = await db_session.execute(stmt)
        record = db_result.scalar_one_or_none()
        assert record is not None
        assert record.deleted_at is not None

    async def test_not_found_returns_none(self, db_session):
        result = await soft_delete_installation(db_session, 99999999)
        assert result is None


class TestGetInstallationByGithubId:
    async def test_finds_installation(self, db_session, test_installation):
        result = await get_installation_by_github_id(
            db_session, test_installation.github_installation_id
        )
        assert result is not None
        assert result.id == test_installation.id

    async def test_excludes_deleted(self, db_session, test_installation):
        test_installation.deleted_at = datetime.now(UTC)
        await db_session.flush()

        result = await get_installation_by_github_id(
            db_session, test_installation.github_installation_id
        )
        assert result is None


class TestGetInstallationAccessToken:
    async def test_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "token": "ghs_test123",
            "expires_at": "2026-01-01T00:00:00Z",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await get_installation_access_token(12345, "fake-jwt")

        assert result["token"] == "ghs_test123"

    async def test_timeout(self):
        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ExternalServiceError, match="temporarily unavailable"):
                await get_installation_access_token(12345, "fake-jwt")

    async def test_401_raises_unauthorized(self):
        mock_response = httpx.Response(401, json={"message": "Bad credentials"})
        mock_response.request = httpx.Request("POST", "https://api.github.com/test")

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(UnauthorizedError):
                await get_installation_access_token(12345, "fake-jwt")


class TestVerifyAdminPermission:
    async def test_org_admin(self, test_installation, test_user, settings):
        user, _ = test_user
        mock_response = MagicMock()
        mock_response.json.return_value = {"role": "admin", "state": "active"}
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await verify_admin_permission(user, test_installation, settings)
        assert result is True

    async def test_org_member_not_admin(self, test_installation, test_user, settings):
        user, _ = test_user
        mock_response = MagicMock()
        mock_response.json.return_value = {"role": "member", "state": "active"}
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ForbiddenError):
                await verify_admin_permission(user, test_installation, settings)

    async def test_user_owner(self, test_user, db_session, settings):
        user, _ = test_user
        user_installation = Installation(
            github_installation_id=11111111,
            account_login="testuser",
            account_id=user.github_id,
            account_type="User",
            repository_selection="all",
            app_slug="helprs",
            target_type="User",
        )
        db_session.add(user_installation)
        await db_session.flush()

        result = await verify_admin_permission(user, user_installation, settings)
        assert result is True

    async def test_user_not_owner(self, test_user, db_session, settings):
        user, _ = test_user
        other_installation = Installation(
            github_installation_id=22222222,
            account_login="otheruser",
            account_id=99999999,
            account_type="User",
            repository_selection="all",
            app_slug="helprs",
            target_type="User",
        )
        db_session.add(other_installation)
        await db_session.flush()

        with pytest.raises(ForbiddenError):
            await verify_admin_permission(user, other_installation, settings)
