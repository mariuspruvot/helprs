"""Integration tests for installation router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.main import create_app
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


@pytest.fixture
async def app_with_db():
    """Create app with a real test database."""
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    application.state.session_factory = session_factory

    yield application

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def authed_client_with_installation(app_with_db):
    """Create an authenticated client with a test user and installation."""
    settings = get_settings()
    session_factory = app_with_db.state.session_factory

    async with session_factory() as session:
        encrypted_token = fernet_encrypt("gho_test_token", settings.FERNET_KEY)
        user = GitHubUser(
            github_id=77777777,
            github_login="routertest",
            email="router@test.com",
            avatar_url=None,
            github_access_token_enc=encrypted_token,
        )
        session.add(user)
        await session.flush()

        installation = Installation(
            github_installation_id=44444444,
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

    jwt_token = create_access_token(
        {"sub": str(user_id), "github_login": "routertest"},
        settings.SECRET_KEY,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app_with_db),
        base_url="http://test",
        headers={"Authorization": f"Bearer {jwt_token}"},
    ) as client:
        yield client, installation


class TestListInstallations:
    async def test_returns_user_installations(self, authed_client_with_installation):
        client, installation = authed_client_with_installation

        # Mock GitHub API /user/installations to return our test installation
        mock_response = MagicMock()
        mock_response.json.return_value = {"installations": [{"id": installation.github_installation_id}]}
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            response = await client.get("/api/v1/installations")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(i["github_installation_id"] == installation.github_installation_id for i in data["items"])

    async def test_without_auth_returns_401(self, app_with_db):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/installations")
        assert response.status_code == 401


class TestGetInstallation:
    async def test_returns_installation_details(self, authed_client_with_installation):
        client, installation = authed_client_with_installation

        # Mock GitHub API for admin permission check
        mock_response = MagicMock()
        mock_response.json.return_value = {"role": "admin", "state": "active"}
        mock_response.raise_for_status = MagicMock()

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            response = await client.get(f"/api/v1/installations/{installation.github_installation_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["github_installation_id"] == installation.github_installation_id
        assert data["account_login"] == "test-org"
