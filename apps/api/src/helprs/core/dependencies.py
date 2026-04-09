"""FastAPI dependency injection providers."""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import Settings, get_settings
from helprs.core.exceptions import UnauthorizedError
from helprs.core.security import decode_access_token

# Re-export get_settings as a dependency
GetSettings = Annotated[Settings, Depends(get_settings)]


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency wired to app.state.session_factory."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    session: DbSession,
    settings: GetSettings,
):
    """Extract and validate Bearer token, return authenticated GitHubUser."""
    from helprs.modules.identity.models import GitHubUser

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")

    token = auth_header.removeprefix("Bearer ")

    try:
        payload = decode_access_token(token, settings.SECRET_KEY)
    except JWTError as e:
        raise UnauthorizedError("Invalid or expired token") from e

    if payload.get("type") == "refresh":
        raise UnauthorizedError("Cannot use refresh token as access token")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid token payload")

    try:
        uuid.UUID(user_id)
    except (ValueError, AttributeError) as e:
        raise UnauthorizedError("Invalid token payload") from e

    result = await session.execute(
        select(GitHubUser).where(GitHubUser.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found")

    return user
