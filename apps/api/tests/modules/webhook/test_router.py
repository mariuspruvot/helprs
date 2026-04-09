"""Integration tests for webhook router."""

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.main import create_app
from tests.modules.webhook.conftest import sign_payload

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
async def app_client(app_with_db):
    """Create a test client from app_with_db."""
    async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def webhook_secret():
    get_settings.cache_clear()
    return get_settings().GITHUB_WEBHOOK_SECRET


class TestWebhookRouter:
    async def test_installation_created_with_valid_hmac(
        self, app_client, webhook_secret, sample_installation_created_payload
    ):
        payload_bytes = json.dumps(sample_installation_created_payload).encode()
        signature = sign_payload(payload_bytes, webhook_secret)

        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_installation_deleted_with_valid_hmac(
        self, app_client, webhook_secret, sample_installation_deleted_payload
    ):
        # First create the installation
        created_payload = {
            **sample_installation_deleted_payload,
            "action": "created",
        }
        created_bytes = json.dumps(created_payload).encode()
        sig = sign_payload(created_bytes, webhook_secret)
        await app_client.post(
            "/api/v1/webhooks/github",
            content=created_bytes,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )

        # Now delete it
        payload_bytes = json.dumps(sample_installation_deleted_payload).encode()
        signature = sign_payload(payload_bytes, webhook_secret)

        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200

    async def test_invalid_hmac_returns_401(self, app_client):
        payload_bytes = b'{"action": "created"}'
        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    async def test_missing_signature_returns_401(self, app_client):
        payload_bytes = b'{"action": "created"}'
        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=payload_bytes,
            headers={
                "X-GitHub-Event": "installation",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401
