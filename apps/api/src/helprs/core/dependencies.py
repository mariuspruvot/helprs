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
from helprs.modules.identity.models import GitHubUser

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


async def _authenticate(request: Request, session: AsyncSession, settings: Settings, token: str) -> GitHubUser:
    """Resolve a bearer token to the user it belongs to."""
    try:
        payload = decode_access_token(token, settings.SECRET_KEY.get_secret_value())
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


def _bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")
    return auth_header.removeprefix("Bearer ")


async def get_current_user(request: Request, session: DbSession, settings: GetSettings) -> GitHubUser:
    """Authenticate from the ``Authorization`` header."""
    return await _authenticate(request, session, settings, _bearer_token(request))


async def get_current_user_for_stream(request: Request, session: DbSession, settings: GetSettings) -> GitHubUser:
    """Authenticate an SSE request, allowing the token in the query string.

    ``EventSource`` cannot set request headers, so a browser opening a stream
    has nowhere else to put the JWT. The cost is real — query strings land in
    proxy logs, browser history and ``Referer`` — so this is granted to the
    streaming endpoints only, never to the whole API.
    """
    token = request.headers.get("Authorization", "").removeprefix("Bearer ") or request.query_params.get(
        "access_token", ""
    )
    if not token:
        raise UnauthorizedError("Missing or invalid Authorization header")
    return await _authenticate(request, session, settings, token)


# Routes take `user: CurrentUser` rather than `user=Depends(get_current_user)`:
# the Annotated form is a real type for the checker and does not trip B008.
CurrentUser = Annotated[GitHubUser, Depends(get_current_user)]
StreamUser = Annotated[GitHubUser, Depends(get_current_user_for_stream)]
