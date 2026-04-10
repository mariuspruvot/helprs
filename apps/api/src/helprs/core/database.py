"""Async SQLAlchemy engine and session factory."""

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from helprs.core.config import get_settings

# Module-level slot holding the active session factory. Populated by
# ``helprs.main`` during lifespan startup and read by ``get_db_context``
# (a plain async context manager — not a FastAPI dependency — used by
# streaming endpoints that need to open a fresh short-lived session
# inside a stream generator AFTER the request-scoped ``get_db`` session
# has already been released).
#
# The FastAPI dep graph keeps using ``app.state.session_factory`` via
# ``core.dependencies.get_db`` — ``get_db_context`` does NOT replace it;
# it is additive, for code paths that live outside the request lifecycle.
_session_factory_holder: async_sessionmaker[AsyncSession] | None = None


def set_session_factory(factory: async_sessionmaker[AsyncSession]) -> None:
    """Register the session factory for ``get_db_context`` to use.

    Called once by the lifespan startup in ``helprs.main`` after the
    engine is created. Tests that need ``get_db_context`` outside the
    app lifespan can call this directly in a fixture.
    """
    global _session_factory_holder
    _session_factory_holder = factory


def clear_session_factory() -> None:
    """Reset the module-level slot (test teardown)."""
    global _session_factory_holder
    _session_factory_holder = None


@asynccontextmanager
async def get_db_context() -> AsyncIterator[AsyncSession]:
    """Open a short-lived AsyncSession outside the FastAPI dep graph.

    Used by SSE streaming code that needs to commit small writes
    (per-question persistence) AFTER the request-scoped
    ``get_db`` dependency has released its session. Holding the
    request-scoped session open across 10s+ LLM calls would exhaust
    the connection pool under load — this helper is the escape hatch.

    Commits on clean exit and rolls back on exception. Never use
    ``get_db_context`` for request-scoped DB work — the FastAPI
    ``get_db`` dependency is the right tool there.
    """
    if _session_factory_holder is None:
        raise RuntimeError(
            "get_db_context called before set_session_factory — "
            "this is a lifespan bug in helprs.main or a missing "
            "test fixture setup."
        )
    async with _session_factory_holder() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class Base(AsyncAttrs, DeclarativeBase):
    """Base model with common columns for all entities."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


def create_engine():
    """Create async SQLAlchemy engine from settings."""
    settings = get_settings()
    return create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=10,
        pool_recycle=3600,
    )


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create async session factory."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager dependency for database sessions."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
