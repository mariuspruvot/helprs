"""Shared fixtures for installation module tests."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


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
async def test_user(db_session, settings):
    """Create a test GitHubUser and return (user, valid_jwt) tuple."""
    user_id = uuid.uuid4()
    encrypted_token = fernet_encrypt("gho_test_token_12345", settings.fernet_keys)
    user = GitHubUser(
        id=user_id,
        github_id=12345678,
        github_login="testuser",
        email="test@example.com",
        avatar_url="https://avatars.githubusercontent.com/u/12345678",
        github_access_token_enc=encrypted_token,
    )
    db_session.add(user)
    await db_session.flush()

    jwt_token = create_access_token(
        {"sub": str(user.id), "github_login": user.github_login},
        settings.SECRET_KEY.get_secret_value(),
    )
    return user, jwt_token


@pytest.fixture
async def test_installation(db_session):
    """Create a test Installation record and return it."""
    installation = Installation(
        github_installation_id=99887766,
        account_login="test-org",
        account_id=55555,
        account_type="Organization",
        repository_selection="all",
        app_slug="helprs",
        target_type="Organization",
        permissions={"pull_requests": "read", "contents": "read"},
        events=["pull_request"],
    )
    db_session.add(installation)
    await db_session.flush()
    return installation
