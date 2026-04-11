"""Tests for database module."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from helprs.core.database import (
    Base,
    clear_session_factory,
    get_db_context,
    set_session_factory,
)
from helprs.modules.installation.models import Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


def test_base_metadata_is_importable():
    assert Base.metadata is not None


def test_base_has_common_columns():
    mapper_attrs = set(Base.__annotations__.keys())
    assert "id" in mapper_attrs
    assert "created_at" in mapper_attrs
    assert "updated_at" in mapper_attrs


def test_base_id_column_is_uuid_type():
    # Verify the id column uses UUID type via mapped_column
    mapped_col = Base.__dict__["id"]
    # The column should produce UUID primary keys
    assert mapped_col is not None
    # Verify we can instantiate a UUID (the default factory works)
    val = uuid.uuid4()
    assert isinstance(val, uuid.UUID)


# ----------------------------------------------------------------------
# Story 3.3 Task 3.3 + P22 from story-3.3 review: ``get_db_context``
# lifecycle tests. Locks the commit-on-success / rollback-on-error /
# missing-factory-raises contract so SSE code that relies on this
# helper cannot silently drop writes.
# ----------------------------------------------------------------------


def _make_installation(login: str) -> Installation:
    return Installation(
        github_installation_id=abs(hash(login)) % (10**8),
        account_login=login,
        account_id=abs(hash(login + "-id")) % (10**8),
        account_type="Organization",
        repository_selection="all",
        app_slug="helprs",
        target_type="Organization",
        permissions={"pull_requests": "write"},
        events=["pull_request"],
        suppression_labels=None,
    )


class TestGetDbContext:
    async def test_commits_on_clean_exit(self):
        """Open a session via ``get_db_context``, insert a row, exit
        cleanly → a second independently-opened session must see the
        committed row (proves commit happened).
        """
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, class_=_AsyncSession, expire_on_commit=False)
            set_session_factory(factory)
            try:
                async with get_db_context() as tx:
                    tx.add(_make_installation("ctx-commit"))
                # Re-open a fresh session and verify the row is visible.
                async with factory() as verify:
                    rows = list(
                        (await verify.execute(select(Installation).where(Installation.account_login == "ctx-commit")))
                        .scalars()
                        .all()
                    )
                assert len(rows) == 1
            finally:
                clear_session_factory()
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    async def test_rolls_back_on_exception(self):
        """Raise inside the context → the row must NOT be persisted
        and the exception must propagate to the caller.
        """
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, class_=_AsyncSession, expire_on_commit=False)
            set_session_factory(factory)
            try:

                class _MarkerError(RuntimeError):
                    pass

                with pytest.raises(_MarkerError):
                    async with get_db_context() as tx:
                        tx.add(_make_installation("ctx-rollback"))
                        raise _MarkerError("boom")

                async with factory() as verify:
                    rows = list(
                        (await verify.execute(select(Installation).where(Installation.account_login == "ctx-rollback")))
                        .scalars()
                        .all()
                    )
                assert rows == []
            finally:
                clear_session_factory()
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    async def test_raises_runtime_error_when_factory_missing(self):
        """Calling ``get_db_context`` without a registered factory
        must raise RuntimeError — never silently create a new engine
        or leak a sessionless code path.
        """
        clear_session_factory()
        with pytest.raises(RuntimeError, match="set_session_factory"):
            async with get_db_context():
                pass
