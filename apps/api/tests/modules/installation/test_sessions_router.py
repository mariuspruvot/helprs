"""Integration tests for installation sessions list endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.main import create_app
from helprs.modules.container.models import ContainerSession, ContainerStatus
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import Installation
from tests.github_double import serving_github

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
            github_id=88888888,
            github_login="sessiontest",
            email="session@test.com",
            avatar_url=None,
            github_access_token_enc=encrypted_token,
        )
        session.add(user)
        await session.flush()

        installation = Installation(
            github_installation_id=33333333,
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
        await session.flush()

        # Create test sessions
        for i in range(3):
            cs = ContainerSession(
                installation_id=installation.id,
                user_id=user.id,
                pr_number=100 + i,
                repo_full_name="test-org/test-repo",
                skill_name="challenge-me",
                status=ContainerStatus.COMPLETED if i < 2 else ContainerStatus.FAILED,
            )
            session.add(cs)

        await session.commit()
        await session.refresh(user)
        await session.refresh(installation)
        user_id = user.id

    jwt_token = create_access_token(
        {"sub": str(user_id), "github_login": "sessiontest"},
        settings.SECRET_KEY,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app_with_db),
        base_url="http://test",
        headers={"Authorization": f"Bearer {jwt_token}"},
    ) as client:
        yield client, installation


def _mock_github_admin():
    """Serve the GitHub calls these routes make (org list, org membership)."""
    return serving_github()


class TestListInstallationSessions:
    async def test_returns_paginated_results(self, authed_client_with_installation):
        client, installation = authed_client_with_installation

        with _mock_github_admin():
            response = await client.get(
                f"/api/v1/installations/{installation.github_installation_id}/sessions?per_page=2"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["per_page"] == 2
        assert data["total_pages"] == 2

    async def test_second_page(self, authed_client_with_installation):
        client, installation = authed_client_with_installation

        with _mock_github_admin():
            response = await client.get(
                f"/api/v1/installations/{installation.github_installation_id}/sessions?page=2&per_page=2"
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["page"] == 2

    async def test_filters_by_status(self, authed_client_with_installation):
        client, installation = authed_client_with_installation

        with _mock_github_admin():
            response = await client.get(
                f"/api/v1/installations/{installation.github_installation_id}/sessions?status=completed"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(item["status"] == "completed" for item in data["items"])

    async def test_filters_by_failed_status(self, authed_client_with_installation):
        client, installation = authed_client_with_installation

        with _mock_github_admin():
            response = await client.get(
                f"/api/v1/installations/{installation.github_installation_id}/sessions?status=failed"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "failed"

    async def test_returns_empty_for_no_sessions(self, app_with_db):
        settings = get_settings()
        session_factory = app_with_db.state.session_factory

        async with session_factory() as session:
            encrypted_token = fernet_encrypt("gho_test_token", settings.FERNET_KEY)
            user = GitHubUser(
                github_id=99999999,
                github_login="emptytest",
                email="empty@test.com",
                avatar_url=None,
                github_access_token_enc=encrypted_token,
            )
            session.add(user)
            await session.flush()

            installation = Installation(
                github_installation_id=22222222,
                account_login="empty-org",
                account_id=66666,
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
            gh_id = installation.github_installation_id

        jwt_token = create_access_token(
            {"sub": str(user_id), "github_login": "emptytest"},
            settings.SECRET_KEY,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
            headers={"Authorization": f"Bearer {jwt_token}"},
        ) as client:
            with _mock_github_admin():
                response = await client.get(f"/api/v1/installations/{gh_id}/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["total_pages"] == 0

    async def test_requires_auth(self, app_with_db):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/installations/33333333/sessions")
        assert response.status_code == 401

    async def test_caps_per_page_at_100(self, authed_client_with_installation):
        client, installation = authed_client_with_installation

        with _mock_github_admin():
            response = await client.get(
                f"/api/v1/installations/{installation.github_installation_id}/sessions?per_page=500"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["per_page"] == 100

    async def test_session_response_fields(self, authed_client_with_installation):
        client, installation = authed_client_with_installation

        with _mock_github_admin():
            response = await client.get(f"/api/v1/installations/{installation.github_installation_id}/sessions")

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert "id" in item
        assert "pr_number" in item
        assert "repo_full_name" in item
        assert "skill_name" in item
        assert "status" in item
        assert "created_at" in item

    async def test_not_found_for_nonexistent_installation(self, authed_client_with_installation):
        client, _ = authed_client_with_installation

        with _mock_github_admin():
            response = await client.get("/api/v1/installations/99999/sessions")

        assert response.status_code == 404
