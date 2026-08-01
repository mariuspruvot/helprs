"""Identity use cases: OAuth login, token issuance, user statistics.

Orchestration only — SQL lives in ``repository``, GitHub calls in ``github``.
"""

import uuid as uuid_mod
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from cryptography.fernet import InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import Settings
from helprs.core.exceptions import UnauthorizedError
from helprs.core.security import (
    create_access_token,
    decode_access_token,
    fernet_decrypt,
    fernet_encrypt,
)
from helprs.modules.container import repository as container_repository
from helprs.modules.identity import github, repository
from helprs.modules.identity.github import GitHubUserProfile
from helprs.modules.identity.models import GitHubUser
from helprs.modules.identity.schemas import DailyCount, StatusTotals, UserStatsResponse
from helprs.modules.installation.service import get_installations_for_user

REFRESH_TOKEN_LIFETIME = timedelta(days=7)
STATS_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class TokenPair:
    """The credentials handed to a browser after a successful login."""

    access_token: str
    refresh_token: str


async def authenticate_with_code(session: AsyncSession, code: str, settings: Settings) -> tuple[GitHubUser, TokenPair]:
    """Complete the OAuth dance: code -> GitHub identity -> local user -> tokens."""
    oauth_token = await github.exchange_code_for_token(code, settings)
    profile = await github.fetch_user_profile(oauth_token.access_token)
    user = await sync_user(session, profile, oauth_token.access_token, settings)
    return user, create_token_pair(user, settings)


async def sync_user(
    session: AsyncSession,
    profile: GitHubUserProfile,
    access_token: str,
    settings: Settings,
) -> GitHubUser:
    """Create the user for this GitHub identity, or refresh the stored one."""
    encrypted_token = fernet_encrypt(access_token, settings.FERNET_KEY.get_secret_value())
    user = await repository.get_by_github_id(session, profile.github_id)

    if user is None:
        return await repository.add(
            session,
            GitHubUser(
                github_id=profile.github_id,
                github_login=profile.login,
                email=profile.email,
                avatar_url=profile.avatar_url,
                github_access_token_enc=encrypted_token,
            ),
        )

    user.github_login = profile.login
    user.email = profile.email
    user.avatar_url = profile.avatar_url
    user.github_access_token_enc = encrypted_token
    await session.flush()
    return user


def get_decrypted_github_token(user: GitHubUser, fernet_key: str) -> str:
    """Decrypt a user's stored GitHub access token."""
    try:
        return fernet_decrypt(user.github_access_token_enc, fernet_key)
    except InvalidToken as e:
        raise UnauthorizedError("Stored GitHub token is corrupted") from e


def create_token_pair(user: GitHubUser, settings: Settings) -> TokenPair:
    """Mint a short-lived access token and a long-lived refresh token."""
    return TokenPair(
        access_token=create_access_token(
            {"sub": str(user.id), "github_login": user.github_login},
            settings.SECRET_KEY.get_secret_value(),
        ),
        refresh_token=create_access_token(
            {"sub": str(user.id), "type": "refresh"},
            settings.SECRET_KEY.get_secret_value(),
            REFRESH_TOKEN_LIFETIME,
        ),
    )


async def refresh_tokens(refresh_token: str, session: AsyncSession, settings: Settings) -> TokenPair:
    """Validate a refresh token and issue a fresh pair."""
    try:
        payload = decode_access_token(refresh_token, settings.SECRET_KEY.get_secret_value())
    except Exception as e:
        raise UnauthorizedError("Invalid or expired refresh token") from e

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Token is not a refresh token")

    user = await repository.get_by_id(session, _parse_subject(payload.get("sub")))
    if not user:
        raise UnauthorizedError("User not found")

    return create_token_pair(user, settings)


def _parse_subject(subject: object) -> uuid_mod.UUID:
    """Read the ``sub`` claim as a UUID, rejecting anything else."""
    if not isinstance(subject, str):
        raise UnauthorizedError("Invalid refresh token payload")
    try:
        return uuid_mod.UUID(subject)
    except ValueError as e:
        raise UnauthorizedError("Invalid refresh token payload") from e


async def get_user_stats(session: AsyncSession, user: GitHubUser, settings: Settings) -> UserStatsResponse:
    """Session activity across every installation the user can reach."""
    installations = await get_installations_for_user(session, user, settings)
    installation_ids = [i.id for i in installations]

    totals = await container_repository.count_by_status(session, installation_ids)
    daily = await container_repository.count_per_day(
        session,
        installation_ids,
        since=datetime.now(UTC) - STATS_WINDOW,
    )

    return UserStatsResponse(
        # The API has always exposed these as timestamps at midnight UTC.
        daily_counts=[DailyCount(date=datetime.combine(d.day, time.min, tzinfo=UTC), count=d.count) for d in daily],
        totals=StatusTotals(
            completed=totals.completed,
            failed=totals.failed,
            timeout=totals.timeout,
            total=totals.total,
        ),
    )
