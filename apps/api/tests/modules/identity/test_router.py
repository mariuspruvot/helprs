"""Integration tests for identity auth endpoints."""

import secrets
from datetime import timedelta

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.main import create_app
from helprs.modules.identity.models import GitHubUser

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


@pytest.fixture
async def app_with_db():
    """Create app with a real test database, set up and torn down per test."""
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
async def authed_client(app_with_db):
    """Provide an AsyncClient with a test user and valid JWT."""
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
        await session.commit()
        await session.refresh(user)
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
        yield client, user_id


class TestGithubLogin:
    async def test_redirects_to_github(self, app_with_db):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/api/v1/auth/github")
            assert resp.status_code == 307
            location = resp.headers["location"]
            assert "github.com/login/oauth/authorize" in location
            assert "client_id=" in location
            assert "read" in location and "user" in location


class TestGithubCallback:
    async def test_valid_callback(self, app_with_db, monkeypatch):
        def _github(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/access_token"):
                return httpx.Response(200, json={"access_token": "gho_callback_token", "token_type": "bearer"})
            return httpx.Response(
                200,
                json={"id": 88888888, "login": "callbackuser", "email": "callback@test.com", "avatar_url": None},
            )

        # Keep a handle on the real client: the ASGI transport below must not
        # be swapped for the GitHub double.
        real_client = httpx.AsyncClient

        def _client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_github)
            return real_client(*args, **kwargs)

        state = secrets.token_urlsafe(32)
        async with real_client(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            client.cookies.set("oauth_state", state)
            monkeypatch.setattr(httpx, "AsyncClient", _client)
            resp = await client.get(f"/api/v1/auth/github/callback?code=test_code&state={state}")

        assert resp.status_code == 307
        assert "access_token=" in resp.headers["location"]
        assert "refresh_token" in resp.headers.get("set-cookie", "")

    async def test_invalid_state(self, app_with_db):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/api/v1/auth/github/callback?code=test&state=invalid")
            assert resp.status_code == 401


class TestAuthMe:
    async def test_returns_user(self, authed_client):
        client, user_id = authed_client
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["github_login"] == "routertest"
        assert data["github_id"] == 77777777

    async def test_no_token_returns_401(self, app_with_db):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/v1/auth/me")
            assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, app_with_db):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
            headers={"Authorization": "Bearer invalid_jwt"},
        ) as client:
            resp = await client.get("/api/v1/auth/me")
            assert resp.status_code == 401


class TestRefresh:
    async def test_valid_refresh(self, authed_client, app_with_db):
        _, user_id = authed_client
        settings = get_settings()

        refresh_token = create_access_token(
            {"sub": str(user_id), "type": "refresh"},
            settings.SECRET_KEY,
            timedelta(days=7),
        )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
        ) as client:
            client.cookies.set("refresh_token", refresh_token)
            resp = await client.post("/api/v1/auth/refresh")
            assert resp.status_code == 200
            data = resp.json()
            assert "access_token" in data

    async def test_missing_refresh_cookie(self, app_with_db):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/v1/auth/refresh")
            assert resp.status_code == 401


class TestLogout:
    async def test_clears_cookie(self, app_with_db):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_db),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/v1/auth/logout")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
