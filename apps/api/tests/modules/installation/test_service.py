"""Unit tests for installation service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select

from helprs.core.config import Settings
from helprs.core.exceptions import ExternalServiceError, ForbiddenError, UnauthorizedError
from helprs.modules.installation.models import Installation
from helprs.modules.installation.service import (
    create_installation,
    get_installation_access_token,
    get_installation_by_github_id,
    mint_installation_token,
    post_pr_comment,
    post_pr_comment_with_retry,
    soft_delete_installation,
    verify_admin_permission,
    verify_installation_access,
    verify_session_access,
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
        result = await soft_delete_installation(db_session, test_installation.github_installation_id)

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
        result = await get_installation_by_github_id(db_session, test_installation.github_installation_id)
        assert result is not None
        assert result.id == test_installation.id

    async def test_excludes_deleted(self, db_session, test_installation):
        test_installation.deleted_at = datetime.now(UTC)
        await db_session.flush()

        result = await get_installation_by_github_id(db_session, test_installation.github_installation_id)
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


# ---------------------------------------------------------------------------
# GitHub client helpers — Story 2.2
# ---------------------------------------------------------------------------


def _make_httpx_client_mock(response: MagicMock) -> MagicMock:
    mock_client = AsyncMock()
    mock_client.post.return_value = response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _fake_settings() -> Settings:
    # ``GITHUB_APP_PRIVATE_KEY`` is only used through ``create_app_jwt`` which
    # we mock; a placeholder string is fine here.
    return Settings(
        DATABASE_URL="postgresql+asyncpg://x",
        SECRET_KEY="x",
        FERNET_KEY="lQFzS7dfbPY3kS9GH7o4g-ykr-J1oz2ZuGsqdbSzNk8=",
        GITHUB_APP_ID="12345",
        GITHUB_APP_PRIVATE_KEY="-----BEGIN FAKE-----",
    )


class TestMintInstallationToken:
    async def test_composes_jwt_and_fetches_token(self):
        fake_settings = _fake_settings()
        with (
            patch(
                "helprs.modules.installation.service.create_app_jwt",
                return_value="fake.jwt.token",
            ) as mock_jwt,
            patch(
                "helprs.modules.installation.service.get_installation_access_token",
                AsyncMock(return_value={"token": "ghs_xyz", "expires_at": "..."}),
            ) as mock_get_token,
        ):
            token = await mint_installation_token(12345678, fake_settings)

        assert token == "ghs_xyz"
        mock_jwt.assert_called_once_with("12345", "-----BEGIN FAKE-----")
        # Unscoped by default: the API's own token keeps full installation
        # scope. Narrowing is opt-in, for the runner container's token.
        mock_get_token.assert_awaited_once_with(12345678, "fake.jwt.token", repositories=None, permissions=None)


class TestPostPRComment:
    async def test_posts_to_correct_url_with_headers(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        mock_client = _make_httpx_client_mock(response)

        with patch(
            "helprs.modules.installation.service.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await post_pr_comment(
                owner="acme",
                repo="repo",
                pr_number=42,
                body="hello",
                installation_token="ghs_xyz",
            )

        mock_client.post.assert_awaited_once()
        call_args = mock_client.post.call_args
        assert call_args.args[0] == "https://api.github.com/repos/acme/repo/issues/42/comments"
        assert call_args.kwargs["json"] == {"body": "hello"}
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer ghs_xyz"
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"


class TestPostPRCommentWithRetry:
    async def test_retries_on_500_then_succeeds(self, monkeypatch):
        monkeypatch.setattr(
            "helprs.modules.installation.service.asyncio.sleep",
            AsyncMock(),
        )

        attempts = 0

        async def flaky(**kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                resp = MagicMock()
                resp.status_code = 503
                raise httpx.HTTPStatusError("boom", request=MagicMock(), response=resp)

        with patch(
            "helprs.modules.installation.service.post_pr_comment",
            side_effect=flaky,
        ):
            await post_pr_comment_with_retry(
                owner="acme",
                repo="repo",
                pr_number=42,
                body="b",
                installation_token="t",
            )

        assert attempts == 3

    async def test_retries_on_transport_error(self, monkeypatch):
        monkeypatch.setattr(
            "helprs.modules.installation.service.asyncio.sleep",
            AsyncMock(),
        )

        calls = 0

        async def flaky(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("refused")

        with patch(
            "helprs.modules.installation.service.post_pr_comment",
            side_effect=flaky,
        ):
            await post_pr_comment_with_retry(
                owner="a",
                repo="r",
                pr_number=1,
                body="b",
                installation_token="t",
            )
        assert calls == 2

    async def test_does_not_retry_on_404(self, monkeypatch):
        monkeypatch.setattr(
            "helprs.modules.installation.service.asyncio.sleep",
            AsyncMock(),
        )

        calls = 0

        async def always_404(**kwargs):
            nonlocal calls
            calls += 1
            resp = MagicMock()
            resp.status_code = 404
            raise httpx.HTTPStatusError("not found", request=MagicMock(), response=resp)

        with (
            patch(
                "helprs.modules.installation.service.post_pr_comment",
                side_effect=always_404,
            ),
            pytest.raises(ExternalServiceError),
        ):
            await post_pr_comment_with_retry(
                owner="a",
                repo="r",
                pr_number=1,
                body="b",
                installation_token="t",
            )
        assert calls == 1  # no retries

    async def test_wraps_final_failure_in_external_service_error(self, monkeypatch):
        monkeypatch.setattr(
            "helprs.modules.installation.service.asyncio.sleep",
            AsyncMock(),
        )

        calls = 0

        async def always_500(**kwargs):
            nonlocal calls
            calls += 1
            resp = MagicMock()
            resp.status_code = 500
            raise httpx.HTTPStatusError("oops", request=MagicMock(), response=resp)

        with (
            patch(
                "helprs.modules.installation.service.post_pr_comment",
                side_effect=always_500,
            ),
            pytest.raises(ExternalServiceError),
        ):
            await post_pr_comment_with_retry(
                owner="a",
                repo="r",
                pr_number=1,
                body="b",
                installation_token="t",
            )
        assert calls == 3


# ---------------------------------------------------------------------------
# Access control — verify_installation_access / verify_session_access
# ---------------------------------------------------------------------------


class TestVerifyInstallationAccess:
    async def test_user_owner_passes(self, test_user, db_session, settings):
        user, _ = test_user
        installation = Installation(
            github_installation_id=33333333,
            account_login="testuser",
            account_id=user.github_id,
            account_type="User",
            repository_selection="all",
            app_slug="helprs",
            target_type="User",
        )
        db_session.add(installation)
        await db_session.flush()

        result = await verify_installation_access(user, installation, settings)
        assert result is True

    async def test_user_non_owner_raises_403(self, test_user, db_session, settings):
        user, _ = test_user
        installation = Installation(
            github_installation_id=44444444,
            account_login="otheruser",
            account_id=99999999,
            account_type="User",
            repository_selection="all",
            app_slug="helprs",
            target_type="User",
        )
        db_session.add(installation)
        await db_session.flush()

        with pytest.raises(ForbiddenError):
            await verify_installation_access(user, installation, settings)

    async def test_org_member_passes(self, test_installation, test_user, settings):
        user, _ = test_user
        mock_response = MagicMock()
        mock_response.json.return_value = [{"login": "test-org"}]
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await verify_installation_access(user, test_installation, settings)
        assert result is True

    async def test_org_non_member_raises_403(self, test_installation, test_user, settings):
        user, _ = test_user
        mock_response = MagicMock()
        mock_response.json.return_value = [{"login": "other-org"}]
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ForbiddenError):
                await verify_installation_access(user, test_installation, settings)


class TestVerifySessionAccess:
    async def test_session_owner_passes_without_api_call(self, test_user, test_installation, db_session, settings):
        from helprs.modules.container.models import ContainerSession, ContainerStatus

        user, _ = test_user
        cs = ContainerSession(
            installation_id=test_installation.id,
            user_id=user.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
            status=ContainerStatus.RUNNING,
            container_id="fake-id",
        )
        db_session.add(cs)
        await db_session.flush()

        # No httpx mock needed — owner path doesn't call GitHub
        result = await verify_session_access(user, cs, db_session, settings)
        assert result is True

    async def test_org_member_can_access_others_session(self, test_user, test_installation, db_session, settings):
        from helprs.modules.container.models import ContainerSession, ContainerStatus
        from helprs.modules.identity.models import GitHubUser

        user, _ = test_user

        # Create a session owned by a different user
        from helprs.core.security import fernet_encrypt

        other_user = GitHubUser(
            github_id=77777777,
            github_login="otherdev",
            email="other@test.com",
            avatar_url=None,
            github_access_token_enc=fernet_encrypt("gho_other", settings.FERNET_KEY),
        )
        db_session.add(other_user)
        await db_session.flush()

        cs = ContainerSession(
            installation_id=test_installation.id,
            user_id=other_user.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
            status=ContainerStatus.RUNNING,
            container_id="fake-id",
        )
        db_session.add(cs)
        await db_session.flush()

        # Mock GitHub /user/orgs to return the installation's org
        mock_response = MagicMock()
        mock_response.json.return_value = [{"login": "test-org"}]
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await verify_session_access(user, cs, db_session, settings)
        assert result is True

    async def test_non_member_cannot_access_session(self, test_user, test_installation, db_session, settings):
        from helprs.modules.container.models import ContainerSession, ContainerStatus
        from helprs.modules.identity.models import GitHubUser

        user, _ = test_user

        from helprs.core.security import fernet_encrypt

        other_user = GitHubUser(
            github_id=66666666,
            github_login="stranger",
            email="stranger@test.com",
            avatar_url=None,
            github_access_token_enc=fernet_encrypt("gho_stranger", settings.FERNET_KEY),
        )
        db_session.add(other_user)
        await db_session.flush()

        cs = ContainerSession(
            installation_id=test_installation.id,
            user_id=other_user.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
            status=ContainerStatus.RUNNING,
            container_id="fake-id",
        )
        db_session.add(cs)
        await db_session.flush()

        # Mock GitHub /user/orgs to return a different org
        mock_response = MagicMock()
        mock_response.json.return_value = [{"login": "unrelated-org"}]
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(ForbiddenError):
                await verify_session_access(user, cs, db_session, settings)
