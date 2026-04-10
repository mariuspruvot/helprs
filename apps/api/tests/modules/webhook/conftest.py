"""Shared fixtures for webhook module tests."""

import hashlib
import hmac

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


def sign_payload(payload: bytes, secret: str) -> str:
    """Generate a valid sha256=... signature for test payloads."""
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.fixture
async def db_session():
    """Provide a transactional database session with tables created/dropped per test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def webhook_secret(settings):
    """Return the webhook secret for test signing."""
    return settings.GITHUB_WEBHOOK_SECRET


@pytest.fixture
def sample_installation_created_payload():
    return {
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


def make_pull_request_payload(action: str = "opened") -> dict:
    """Minimal pull_request webhook payload for tests."""
    return {
        "action": action,
        "installation": {"id": 12345678},
        "pull_request": {
            "number": 42,
            "title": "Add foo",
            "diff_url": "https://github.com/acme/repo/pull/42.diff",
            "head": {"sha": "abc123"},
        },
        "repository": {
            "id": 999,
            "full_name": "acme/repo",
            "name": "repo",
            "owner": {"login": "acme"},
        },
        "sender": {"login": "dev-user", "id": 1},
    }


@pytest.fixture
def pull_request_opened_payload():
    return make_pull_request_payload("opened")


@pytest.fixture
def pull_request_synchronize_payload():
    return make_pull_request_payload("synchronize")


@pytest.fixture
def sample_installation_deleted_payload():
    return {
        "action": "deleted",
        "installation": {
            "id": 12345678,
            "account": {"login": "myorg", "id": 99999, "type": "Organization"},
            "repository_selection": "selected",
            "app_slug": "helprs",
            "target_type": "Organization",
            "permissions": {},
            "events": [],
            "suspended_at": None,
        },
        "sender": {"login": "admin-user", "id": 111},
    }
