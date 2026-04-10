"""Comprehension repository implementations.

``SqlAlchemySessionRepository`` is the concrete implementation of the
domain ``SessionRepository`` protocol. It owns the ORM ↔ domain mapping
for ``SessionModel`` ↔ ``Session``.

Unit-of-work rule: this repository never calls ``session.commit()``. The
outer handler (``StartSessionHandler``) and, above that,
``process_webhook_event`` own the transaction boundary so exceptions roll
back cleanly. This is deliberately the opposite of the webhook repository
(which commits eagerly to survive crashes).
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.comprehension.domain.entities import PRContext, Session
from helprs.modules.comprehension.domain.value_objects import SessionRole, SessionStatus
from helprs.modules.comprehension.infrastructure.models import SessionModel


def _to_domain(row: SessionModel) -> Session:
    """Map an ORM row to a domain ``Session``.

    Kept private to this module — mapping is infrastructure plumbing and
    must not leak into ``domain/entities.py``.
    """
    return Session(
        id=row.id,
        installation_id=row.installation_id,
        github_installation_id=row.github_installation_id,
        repo_full_name=row.repo_full_name,
        repo_owner=row.repo_owner,
        repo_name=row.repo_name,
        pr_number=row.pr_number,
        pr_title=row.pr_title,
        pr_head_sha=row.pr_head_sha,
        pr_diff_url=row.pr_diff_url,
        role=SessionRole(row.role),
        status=SessionStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemySessionRepository:
    """Concrete ``SessionRepository`` backed by an AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_pair(self, *, pr_ctx: PRContext) -> tuple[Session, Session]:
        """Insert an (author, reviewer) pair and flush to assign IDs."""
        shared = pr_ctx.to_columns()
        author = SessionModel(role=SessionRole.AUTHOR.value, status=SessionStatus.PENDING.value, **shared)
        reviewer = SessionModel(role=SessionRole.REVIEWER.value, status=SessionStatus.PENDING.value, **shared)
        self._session.add_all((author, reviewer))
        # Flush — not commit — so the caller retains unit-of-work control.
        # IDs + created_at/updated_at are populated here.
        await self._session.flush()
        await self._session.refresh(author)
        await self._session.refresh(reviewer)
        return _to_domain(author), _to_domain(reviewer)

    async def find_pair(
        self,
        *,
        installation_id: UUID,
        repo_full_name: str,
        pr_number: int,
    ) -> list[Session]:
        """Return 0, 1 (corrupted), or 2 rows for the PR."""
        result = await self._session.execute(
            select(SessionModel)
            .where(
                SessionModel.installation_id == installation_id,
                SessionModel.repo_full_name == repo_full_name,
                SessionModel.pr_number == pr_number,
            )
            .order_by(SessionModel.role)
        )
        rows = list(result.scalars().all())
        return [_to_domain(r) for r in rows]

    async def update_head_sha(
        self,
        *,
        installation_id: UUID,
        repo_full_name: str,
        pr_number: int,
        new_head_sha: str,
        new_pr_title: str,
        new_pr_diff_url: str,
    ) -> list[Session]:
        """Update PR-head metadata on both rows of an existing pair.

        Uses a single ``update(...).where(...)`` — no per-row roundtrip.
        The subsequent ``SELECT`` returns the refreshed domain entities so
        callers can log / inspect them.
        """
        stmt = (
            update(SessionModel)
            .where(
                SessionModel.installation_id == installation_id,
                SessionModel.repo_full_name == repo_full_name,
                SessionModel.pr_number == pr_number,
            )
            .values(
                pr_head_sha=new_head_sha,
                pr_title=new_pr_title,
                pr_diff_url=new_pr_diff_url,
            )
            .execution_options(synchronize_session=False)
        )
        await self._session.execute(stmt)
        await self._session.flush()
        # Re-fetch: the UPDATE statement doesn't populate Python-side objects
        # and ``updated_at`` is refreshed server-side by the ``onupdate`` hook.
        return await self.find_pair(
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
        )

    async def delete_one(self, *, session_id: UUID) -> None:
        """Delete a single session row by id.

        Used by the handler's orphan-recovery path (1-row case in
        ``find_pair``). Intentionally narrow — no bulk/delete-by-PR surface
        area; Story 3.1 will decide the lifecycle story for delete.
        """
        row = await self._session.get(SessionModel, session_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
