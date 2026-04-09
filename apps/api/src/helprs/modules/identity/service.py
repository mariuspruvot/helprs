"""Identity and OAuth business logic."""

import uuid as uuid_mod
from datetime import timedelta

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import Settings
from helprs.core.exceptions import ExternalServiceError, UnauthorizedError
from helprs.core.security import (
    create_access_token,
    decode_access_token,
    fernet_decrypt,
    fernet_encrypt,
)
from helprs.modules.identity.models import GitHubUser

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


async def exchange_code_for_token(code: str, settings: Settings) -> dict:
    """Exchange OAuth authorization code for a GitHub access token."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        raise ExternalServiceError("GitHub token exchange failed") from e

    data = resp.json()
    if "error" in data:
        raise UnauthorizedError(f"GitHub OAuth error: {data['error']}")
    return data


async def fetch_github_user(access_token: str) -> dict:
    """Fetch the authenticated user's profile from GitHub."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise UnauthorizedError("GitHub token is invalid or revoked") from e
        raise ExternalServiceError("GitHub API error") from e

    return resp.json()


async def get_or_create_user(
    session: AsyncSession,
    github_user_data: dict,
    access_token: str,
    settings: Settings,
) -> GitHubUser:
    """Create or update a GitHubUser record by github_id."""
    github_id = github_user_data["id"]
    encrypted_token = fernet_encrypt(access_token, settings.FERNET_KEY)

    result = await session.execute(select(GitHubUser).where(GitHubUser.github_id == github_id))
    user = result.scalar_one_or_none()

    if user:
        user.github_login = github_user_data["login"]
        user.email = github_user_data.get("email")
        user.avatar_url = github_user_data.get("avatar_url")
        user.github_access_token_enc = encrypted_token
    else:
        user = GitHubUser(
            github_id=github_id,
            github_login=github_user_data["login"],
            email=github_user_data.get("email"),
            avatar_url=github_user_data.get("avatar_url"),
            github_access_token_enc=encrypted_token,
        )
        session.add(user)

    await session.flush()
    return user


def get_decrypted_github_token(user: GitHubUser, fernet_key: str) -> str:
    """Decrypt a user's stored GitHub access token."""
    try:
        return fernet_decrypt(user.github_access_token_enc, fernet_key)
    except InvalidToken as e:
        raise UnauthorizedError("Stored GitHub token is corrupted") from e


def create_token_pair(user: GitHubUser, settings: Settings) -> tuple[str, str]:
    """Create a JWT access token (15 min) and refresh token (7 days)."""
    access_token = create_access_token(
        {"sub": str(user.id), "github_login": user.github_login},
        settings.SECRET_KEY,
    )
    refresh_token = create_access_token(
        {"sub": str(user.id), "type": "refresh"},
        settings.SECRET_KEY,
        timedelta(days=7),
    )
    return access_token, refresh_token


async def refresh_tokens(
    refresh_token: str,
    session: AsyncSession,
    settings: Settings,
) -> tuple[str, str]:
    """Validate a refresh token and issue a new token pair."""
    try:
        payload = decode_access_token(refresh_token, settings.SECRET_KEY)
    except Exception as e:
        raise UnauthorizedError("Invalid or expired refresh token") from e

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Token is not a refresh token")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Invalid refresh token payload")

    try:
        uuid_mod.UUID(user_id)
    except (ValueError, AttributeError) as e:
        raise UnauthorizedError("Invalid refresh token payload") from e

    result = await session.execute(select(GitHubUser).where(GitHubUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found")

    return create_token_pair(user, settings)
