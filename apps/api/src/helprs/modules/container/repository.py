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

from helprs.modules.container.models import ContainerSession, ContainerStatus


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
            func.count(ContainerSession.id).label("count"),
        )
        .where(
            ContainerSession.installation_id.in_(installation_ids),
            ContainerSession.created_at >= since,
        )
        .group_by("day")
        .order_by("day")
    )
    return [DailyCount(day=row.day, count=row.count) for row in result.all()]


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
