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
    """Extract and validate Bearer token, return authenticated GitHubUser.

    Token sources, in priority order:

    1. ``Authorization: Bearer <token>`` header — preferred for all
       normal API calls (apiFetch sets it).
    2. ``?access_token=<token>`` query parameter — fallback used by SSE
       endpoints. ``EventSource`` cannot set custom request headers, so
       the SSE caller must put the JWT in the URL. The query-param path
       was added 2026-04-11 alongside the Story 3-3 SSE manual-QA fix.
       Trade-off: query params land in access logs and browser history,
       which is acceptable for a 30-min JWT but not ideal — preferred
       long-term solution is fetch+ReadableStream (deferred).
    """
    from helprs.modules.identity.models import GitHubUser

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
    else:
        token = request.query_params.get("access_token") or ""
        if not token:
            raise UnauthorizedError("Missing or invalid Authorization header")

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

    result = await session.execute(select(GitHubUser).where(GitHubUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found")

    return user
