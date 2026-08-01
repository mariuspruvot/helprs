"""Persistence for installations and their BYOK credentials.

Every query lives here, including the soft-delete predicate — a use case that
forgets ``deleted_at IS NULL`` is a bug this module makes impossible.
"""

import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from helprs.modules.installation.models import BYOKConfig, Installation


def _active() -> Select[tuple[Installation]]:
    return select(Installation).where(Installation.deleted_at.is_(None))


async def get_by_github_id(session: AsyncSession, github_installation_id: int) -> Installation | None:
    result = await session.execute(_active().where(Installation.github_installation_id == github_installation_id))
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, installation_id: uuid.UUID) -> Installation | None:
    result = await session.execute(_active().where(Installation.id == installation_id))
    return result.scalar_one_or_none()


async def list_visible_to(
    session: AsyncSession,
    *,
    user_github_id: int,
    org_logins: set[str],
) -> list[Installation]:
    """Installations the user may see, filtered in SQL rather than in Python.

    An installation is visible when the user owns the account it is installed
    on, or when it belongs to one of ``org_logins``. Keeping the predicate in
    the query means the database never hands back another tenant's rows.
    """
    predicates = [
        (Installation.account_type == "User") & (Installation.account_id == user_github_id),
    ]
    if org_logins:
        # GitHub logins are case-insensitive; compare lowercased on both sides.
        predicates.append(
            (Installation.account_type == "Organization")
            & (func.lower(Installation.account_login).in_(sorted(org_logins)))
        )

    result = await session.execute(_active().where(or_(*predicates)).options(selectinload(Installation.byok_config)))
    return list(result.scalars().all())


async def has_organization_installs(session: AsyncSession) -> bool:
    """Whether any Org-type install exists — lets callers skip the /user/orgs call."""
    result = await session.execute(_active().where(Installation.account_type == "Organization").limit(1))
    return result.scalar_one_or_none() is not None


async def load_byok_config(session: AsyncSession, installation: Installation) -> Installation:
    """Eagerly attach ``byok_config`` to an already-loaded installation."""
    await session.refresh(installation, ["byok_config"])
    return installation


async def add(session: AsyncSession, installation: Installation) -> Installation | None:
    """Insert an installation, tolerating a concurrent duplicate.

    Returns ``None`` when the flush failed for a reason other than the unique
    constraint, so the caller can re-raise with its own context.
    """
    session.add(installation)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return None
    return installation


async def get_byok_config(session: AsyncSession, installation_id: uuid.UUID) -> BYOKConfig | None:
    result = await session.execute(select(BYOKConfig).where(BYOKConfig.installation_id == installation_id))
    return result.scalar_one_or_none()


async def add_byok_config(session: AsyncSession, config: BYOKConfig) -> BYOKConfig:
    session.add(config)
    await session.flush()
    return config


async def delete_byok_config(session: AsyncSession, config: BYOKConfig) -> None:
    await session.delete(config)
    await session.flush()


async def list_all_byok_configs(session: AsyncSession) -> list[BYOKConfig]:
    """Every BYOK row, including those of soft-deleted installations.

    Deliberately not filtered by ``_active()``: a retired Fernet key cannot be
    dropped while any stored ciphertext still needs it, and a soft-deleted
    installation's row is still stored ciphertext.
    """
    result = await session.execute(select(BYOKConfig).order_by(BYOKConfig.created_at))
    return list(result.scalars().all())
