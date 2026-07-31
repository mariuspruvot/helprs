"""Persistence for container sessions and their events.

Container sessions belong to this module, so every query against them lives
here — including the aggregates other modules need. That keeps the identity
dashboard from writing SQL over tables it does not own.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from helprs.modules.container.models import ContainerSession, ContainerStatus, SessionEvent


@dataclass(frozen=True)
class StatusCounts:
    """Session totals per terminal status, for one set of installations."""

    completed: int
    failed: int
    timeout: int
    total: int

    @classmethod
    def empty(cls) -> "StatusCounts":
        return cls(completed=0, failed=0, timeout=0, total=0)


@dataclass(frozen=True)
class DailyCount:
    """How many sessions ran on a given day."""

    day: date
    count: int


UNFINISHED_STATUSES = (ContainerStatus.RUNNING, ContainerStatus.PENDING)


async def get(session: AsyncSession, session_id: uuid.UUID) -> ContainerSession | None:
    result = await session.execute(select(ContainerSession).where(ContainerSession.id == session_id))
    return result.scalar_one_or_none()


async def add(session: AsyncSession, container_session: ContainerSession) -> ContainerSession:
    session.add(container_session)
    await session.flush()
    return container_session


async def delete(session: AsyncSession, container_session: ContainerSession) -> None:
    """Delete a session; its events go with it via ON DELETE CASCADE."""
    await session.delete(container_session)
    await session.flush()


async def list_unfinished(
    session: AsyncSession,
    *,
    created_before: datetime | None = None,
) -> list[ContainerSession]:
    """Sessions still marked RUNNING or PENDING, optionally older than a cutoff."""
    query = select(ContainerSession).where(ContainerSession.status.in_(UNFINISHED_STATUSES))
    if created_before is not None:
        query = query.where(ContainerSession.created_at < created_before)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_events(session: AsyncSession, session_id: uuid.UUID) -> list[SessionEvent]:
    """Every persisted event for a session, in arrival order."""
    result = await session.execute(
        select(SessionEvent).where(SessionEvent.session_id == session_id).order_by(SessionEvent.event_id)
    )
    return list(result.scalars().all())


async def count_by_status(session: AsyncSession, installation_ids: list[uuid.UUID]) -> StatusCounts:
    """Count sessions per terminal status across the given installations."""
    if not installation_ids:
        return StatusCounts.empty()

    result = await session.execute(
        select(
            func.count(ContainerSession.id).label("total"),
            func.count(case((ContainerSession.status == ContainerStatus.COMPLETED, 1))).label("completed"),
            func.count(case((ContainerSession.status == ContainerStatus.FAILED, 1))).label("failed"),
            func.count(case((ContainerSession.status == ContainerStatus.TIMEOUT, 1))).label("timeout"),
        ).where(ContainerSession.installation_id.in_(installation_ids))
    )
    row = result.one()
    return StatusCounts(
        completed=row.completed,
        failed=row.failed,
        timeout=row.timeout,
        total=row.total,
    )


async def count_per_day(
    session: AsyncSession,
    installation_ids: list[uuid.UUID],
    *,
    since: datetime,
) -> list[DailyCount]:
    """Count sessions per calendar day since ``since``, oldest first."""
    if not installation_ids:
        return []

    result = await session.execute(
        select(
            cast(ContainerSession.created_at, Date).label("day"),
            # Not labelled "count": that shadows Sequence.count on the Row.
            func.count(ContainerSession.id).label("sessions"),
        )
        .where(
            ContainerSession.installation_id.in_(installation_ids),
            ContainerSession.created_at >= since,
        )
        .group_by("day")
        .order_by("day")
    )
    return [DailyCount(day=row.day, count=row.sessions) for row in result.all()]


async def list_for_installation(
    session: AsyncSession,
    installation_id: uuid.UUID,
    *,
    page: int,
    per_page: int,
    status: ContainerStatus | None = None,
) -> tuple[list[ContainerSession], int]:
    """One page of sessions, newest first, plus the unpaginated total."""
    where = [ContainerSession.installation_id == installation_id]
    if status is not None:
        where.append(ContainerSession.status == status)

    total = await session.scalar(select(func.count()).select_from(ContainerSession).where(*where))

    result = await session.execute(
        select(ContainerSession)
        .where(*where)
        .order_by(ContainerSession.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return list(result.scalars().all()), total or 0


async def count_grouped_by_installation(
    session: AsyncSession,
    installation_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Session count per installation — one GROUP BY, never a query per row."""
    if not installation_ids:
        return {}

    result = await session.execute(
        select(ContainerSession.installation_id, func.count(ContainerSession.id))
        .where(ContainerSession.installation_id.in_(installation_ids))
        .group_by(ContainerSession.installation_id)
    )
    return {installation_id: count for installation_id, count in result.all()}
