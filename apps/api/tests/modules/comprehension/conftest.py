"""Shared fixtures for comprehension module tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.database import Base
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
async def session_factory_fixture():
    """Expose a raw ``async_sessionmaker`` for tests that need to open a
    *second* session (e.g. to verify commit visibility across sessions).
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def test_installation(db_session):
    """Create an Installation row (parent for session rows)."""
    installation = Installation(
        github_installation_id=12345678,
        account_login="acme",
        account_id=55555,
        account_type="Organization",
        repository_selection="all",
        app_slug="helprs",
        target_type="Organization",
        permissions={"pull_requests": "write", "issues": "write"},
        events=["pull_request"],
        suppression_labels=None,
    )
    db_session.add(installation)
    await db_session.flush()
    return installation
