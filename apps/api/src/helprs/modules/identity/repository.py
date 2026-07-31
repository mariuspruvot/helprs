"""Persistence for GitHub user identities.

Every query against ``github_users`` lives here; services above never build
SQL and never see an ``AsyncSession`` method other than through this module.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.identity.models import GitHubUser


async def get_by_github_id(session: AsyncSession, github_id: int) -> GitHubUser | None:
    result = await session.execute(select(GitHubUser).where(GitHubUser.github_id == github_id))
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> GitHubUser | None:
    result = await session.execute(select(GitHubUser).where(GitHubUser.id == user_id))
    return result.scalar_one_or_none()


async def add(session: AsyncSession, user: GitHubUser) -> GitHubUser:
    """Stage a new user and flush so its generated id is available."""
    session.add(user)
    await session.flush()
    return user
