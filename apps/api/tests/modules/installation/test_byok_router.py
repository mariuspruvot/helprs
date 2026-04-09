"""Integration tests for BYOK and settings router endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.main import create_app
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import BYOKConfig, Installation
from helprs.modules.installation.service import configure_byok

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


def _mock_admin_permission():
    """Context manager that mocks GitHub API to return admin role."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"role": "admin", "state": "active"}
    mock_response.raise_for_status = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    return patch(
        "helprs.modules.installation.service.httpx.AsyncClient",
        return_value=mock_client,
    )


@pytest.fixture
async def app_with_db():
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    application.state.session_factory = session_factory

    yield application, session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def authed_client(app_with_db):
    application, session_factory = app_with_db
    settings = get_settings()

    async with session_factory() as session:
        encrypted_token = fernet_encrypt("gho_test_token", settings.FERNET_KEY)
        user = GitHubUser(
            github_id=88888888,
            github_login="byoktest",
            email="byok@test.com",
            avatar_url=None,
            github_access_token_enc=encrypted_token,
        )
        session.add(user)
        await session.flush()

        installation = Installation(
            github_installation_id=55555555,
            account_login="test-org",
            account_id=55555,
            account_type="Organization",
            repository_selection="all",
            app_slug="helprs",
            target_type="Organization",
            permissions={"pull_requests": "read"},
            events=["pull_request"],
        )
        session.add(installation)
        await session.commit()
        await session.refresh(user)
        await session.refresh(installation)
        user_id = user.id
        inst_github_id = installation.github_installation_id

    jwt_token = create_access_token(
        {"sub": str(user_id), "github_login": "byoktest"},
        settings.SECRET_KEY,
    )

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
        headers={"Authorization": f"Bearer {jwt_token}"},
    ) as client:
        yield client, inst_github_id, session_factory


class TestPostByok:
    async def test_valid_key(self, authed_client):
        client, inst_id, _ = authed_client

        with _mock_admin_permission(), patch(
            "helprs.modules.installation.service.validate_anthropic_api_key",
            return_value=True,
        ):
            response = await client.post(
                f"/api/v1/installations/{inst_id}/byok",
                json={"api_key": "sk-ant-api03-testkey1234"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["key_hint"] == "...1234"
        assert data["key_status"] == "valid"
        assert "validated_at" in data

    async def test_invalid_key(self, authed_client):
        client, inst_id, _ = authed_client

        with _mock_admin_permission(), patch(
            "helprs.modules.installation.service.validate_anthropic_api_key",
            return_value=False,
        ):
            response = await client.post(
                f"/api/v1/installations/{inst_id}/byok",
                json={"api_key": "sk-ant-api03-badkey-invalid-12345"},
            )

        assert response.status_code == 400
        data = response.json()
        assert "validation failed" in data["message"]

    async def test_not_admin_returns_403(self, authed_client):
        client, inst_id, _ = authed_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"role": "member", "state": "active"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "helprs.modules.installation.service.httpx.AsyncClient",
            return_value=mock_client,
        ):
            response = await client.post(
                f"/api/v1/installations/{inst_id}/byok",
                json={"api_key": "sk-ant-api03-testkey"},
            )

        assert response.status_code == 403

    async def test_unauthenticated_returns_401(self, app_with_db):
        application, _ = app_with_db
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/installations/55555555/byok",
                json={"api_key": "sk-ant-api03-test"},
            )
        assert response.status_code == 401


class TestDeleteByok:
    async def test_delete_returns_204(self, authed_client):
        client, inst_id, session_factory = authed_client

        # First create a BYOK config
        with _mock_admin_permission(), patch(
            "helprs.modules.installation.service.validate_anthropic_api_key",
            return_value=True,
        ):
            await client.post(
                f"/api/v1/installations/{inst_id}/byok",
                json={"api_key": "sk-ant-api03-deltest1"},
            )

        with _mock_admin_permission():
            response = await client.delete(f"/api/v1/installations/{inst_id}/byok")

        assert response.status_code == 204


class TestPutSuppressionLabels:
    async def test_valid_labels(self, authed_client):
        client, inst_id, _ = authed_client

        with _mock_admin_permission():
            response = await client.put(
                f"/api/v1/installations/{inst_id}/suppression-labels",
                json={"labels": ["hotfix", "wip", "draft"]},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["labels"] == ["hotfix", "wip", "draft"]


class TestGetInstallationIncludesByokStatus:
    async def test_includes_byok_fields(self, authed_client):
        client, inst_id, _ = authed_client

        # Configure BYOK first
        with _mock_admin_permission(), patch(
            "helprs.modules.installation.service.validate_anthropic_api_key",
            return_value=True,
        ):
            await client.post(
                f"/api/v1/installations/{inst_id}/byok",
                json={"api_key": "sk-ant-api03-hintkey1"},
            )

        with _mock_admin_permission():
            response = await client.get(f"/api/v1/installations/{inst_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["byok_configured"] is True
        assert data["byok_key_hint"] == "...key1"
        assert data["byok_key_status"] == "valid"
        assert data["byok_validated_at"] is not None

    async def test_without_byok_shows_unconfigured(self, authed_client):
        client, inst_id, _ = authed_client

        with _mock_admin_permission():
            response = await client.get(f"/api/v1/installations/{inst_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["byok_configured"] is False
        assert data["byok_key_hint"] is None
