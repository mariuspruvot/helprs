"""Async SQLAlchemy engine and session factory."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from helprs.core.config import get_settings


class Base(DeclarativeBase):
    """Base model with common columns for all entities."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(UTC),
    )


def create_engine():
    """Create async SQLAlchemy engine from settings."""
    settings = get_settings()
    return create_async_engine(settings.DATABASE_URL, echo=False)


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
