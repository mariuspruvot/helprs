"""Installation business logic."""

import re
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import Settings
from helprs.core.exceptions import (
    BYOKKeyInvalidError,
    DomainValidationError,
    ExternalServiceError,
    ForbiddenError,
    UnauthorizedError,
)
from helprs.core.security import fernet_decrypt, fernet_encrypt
from helprs.modules.installation.models import BYOKConfig, Installation

logger = structlog.get_logger()

GITHUB_API_BASE = "https://api.github.com"
ANTHROPIC_API_BASE = "https://api.anthropic.com"


async def get_installation_access_token(installation_id: int, app_jwt: str) -> dict:
    """Exchange an App JWT for a scoped installation access token."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise UnauthorizedError("GitHub App JWT is invalid or expired") from e
        raise ExternalServiceError(
            f"GitHub API error: {e.response.status_code}"
        ) from e
    return resp.json()


async def create_installation(session: AsyncSession, webhook_data: dict) -> Installation:
    """Create an installation record from an installation.created webhook payload.

    Handles duplicate webhooks gracefully via upsert logic.
    """
    try:
        inst_data = webhook_data["installation"]
        github_installation_id = inst_data["id"]
        account = inst_data["account"]
        account_login = account["login"]
        account_id = account["id"]
        account_type = account["type"]
    except (KeyError, TypeError) as e:
        await logger.awarning("webhook_payload_malformed", error=str(e))
        raise ValueError(f"Malformed webhook payload: missing {e}") from e

    # Check for existing installation (idempotent handling of duplicate webhooks)
    existing = await get_installation_by_github_id(session, github_installation_id)
    if existing:
        await logger.ainfo(
            "installation_already_exists",
            github_installation_id=github_installation_id,
        )
        return existing

    installation = Installation(
        github_installation_id=github_installation_id,
        account_login=account_login,
        account_id=account_id,
        account_type=account_type,
        repository_selection=inst_data.get("repository_selection", "all"),
        app_slug=inst_data.get("app_slug", ""),
        target_type=inst_data.get("target_type", "Organization"),
        permissions=inst_data.get("permissions"),
        events=inst_data.get("events"),
        suspended_at=None,
    )
    session.add(installation)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await get_installation_by_github_id(session, github_installation_id)
        if existing:
            return existing
        raise
    await logger.ainfo(
        "installation_created",
        github_installation_id=github_installation_id,
        account_login=account_login,
    )
    return installation


async def soft_delete_installation(
    session: AsyncSession, github_installation_id: int
) -> Installation | None:
    """Soft-delete an installation by setting deleted_at. Returns None if not found."""
    result = await session.execute(
        select(Installation).where(
            Installation.github_installation_id == github_installation_id,
            Installation.deleted_at.is_(None),
        )
    )
    installation = result.scalar_one_or_none()
    if not installation:
        return None
    installation.deleted_at = datetime.now(UTC)
    await session.flush()
    await logger.ainfo(
        "installation_soft_deleted",
        github_installation_id=github_installation_id,
    )
    return installation


async def suspend_installation(
    session: AsyncSession, github_installation_id: int
) -> Installation | None:
    """Set suspended_at on an installation."""
    result = await session.execute(
        select(Installation).where(
            Installation.github_installation_id == github_installation_id,
            Installation.deleted_at.is_(None),
        )
    )
    installation = result.scalar_one_or_none()
    if not installation:
        return None
    installation.suspended_at = datetime.now(UTC)
    await session.flush()
    await logger.ainfo(
        "installation_suspended",
        github_installation_id=github_installation_id,
    )
    return installation


async def unsuspend_installation(
    session: AsyncSession, github_installation_id: int
) -> Installation | None:
    """Clear suspended_at on an installation."""
    result = await session.execute(
        select(Installation).where(
            Installation.github_installation_id == github_installation_id,
            Installation.deleted_at.is_(None),
        )
    )
    installation = result.scalar_one_or_none()
    if not installation:
        return None
    installation.suspended_at = None
    await session.flush()
    await logger.ainfo(
        "installation_unsuspended",
        github_installation_id=github_installation_id,
    )
    return installation


async def get_installation_by_github_id(
    session: AsyncSession, github_installation_id: int
) -> Installation | None:
    """Lookup installation by GitHub ID, excluding soft-deleted records."""
    result = await session.execute(
        select(Installation).where(
            Installation.github_installation_id == github_installation_id,
            Installation.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_installations_for_user(
    session: AsyncSession, user, settings: Settings
) -> list[Installation]:
    """Get installations the user has access to via the GitHub API."""
    try:
        github_token = fernet_decrypt(user.github_access_token_enc, settings.FERNET_KEY)
    except InvalidToken as e:
        raise UnauthorizedError("Stored GitHub token is corrupted") from e

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/user/installations",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise UnauthorizedError("GitHub token is invalid or revoked") from e
        raise ExternalServiceError(
            f"GitHub API error: {e.response.status_code}"
        ) from e

    user_installation_ids = {
        inst["id"] for inst in resp.json().get("installations", [])
    }

    if not user_installation_ids:
        return []

    result = await session.execute(
        select(Installation).where(
            Installation.github_installation_id.in_(user_installation_ids),
            Installation.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def verify_admin_permission(
    user, installation: Installation, settings: Settings
) -> bool:
    """Verify user has admin permission on the installation's org/repo."""
    try:
        github_token = fernet_decrypt(user.github_access_token_enc, settings.FERNET_KEY)
    except InvalidToken as e:
        raise UnauthorizedError("Stored GitHub token is corrupted") from e

    if installation.account_type == "User":
        if user.github_id == installation.account_id:
            return True
        raise ForbiddenError("You do not have admin access to this installation")

    # Organization: check membership role
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/orgs/{installation.account_login}/memberships/{user.github_login}",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise UnauthorizedError("GitHub token is invalid or revoked") from e
        if e.response.status_code in (403, 404):
            raise ForbiddenError(
                "You do not have admin access to this installation"
            ) from e
        raise ExternalServiceError(
            f"GitHub API error: {e.response.status_code}"
        ) from e

    membership = resp.json()
    if membership.get("role") != "admin" or membership.get("state") != "active":
        raise ForbiddenError("You do not have admin access to this installation")
    return True


# --- BYOK Services ---


async def validate_anthropic_api_key(api_key: str) -> bool:
    """Validate an Anthropic API key by calling the models list endpoint."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{ANTHROPIC_API_BASE}/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            if response.status_code == 200:
                return True
            if response.status_code in (401, 403):
                return False
            response.raise_for_status()
            return False
    except httpx.TimeoutException as e:
        raise ExternalServiceError("Anthropic API is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        raise ExternalServiceError(
            f"Anthropic API error: {e.response.status_code}"
        ) from e
    except httpx.TransportError as e:
        raise ExternalServiceError("Anthropic API is temporarily unavailable") from e


async def configure_byok(
    session: AsyncSession,
    installation_id: uuid.UUID,
    api_key: str,
    fernet_key: str,
) -> BYOKConfig:
    """Configure BYOK key for an installation. Validates, encrypts, and upserts."""
    is_valid = await validate_anthropic_api_key(api_key)
    if not is_valid:
        raise BYOKKeyInvalidError(
            "API key validation failed -- check your key and try again"
        )

    encrypted_key = fernet_encrypt(api_key, fernet_key)
    key_hint = f"...{api_key[-4:]}"
    now = datetime.now(UTC)

    # Upsert: check if config already exists
    existing = await get_byok_config(session, installation_id)
    if existing:
        existing.encrypted_api_key = encrypted_key
        existing.key_status = "valid"
        existing.validated_at = now
        existing.key_hint = key_hint
        await session.flush()
        await logger.ainfo("byok_config_updated", installation_id=str(installation_id))
        return existing

    config = BYOKConfig(
        installation_id=installation_id,
        encrypted_api_key=encrypted_key,
        key_status="valid",
        validated_at=now,
        key_hint=key_hint,
    )
    session.add(config)
    await session.flush()
    await logger.ainfo("byok_config_created", installation_id=str(installation_id))
    return config


async def get_byok_config(
    session: AsyncSession, installation_id: uuid.UUID
) -> BYOKConfig | None:
    """Get BYOK config for an installation."""
    result = await session.execute(
        select(BYOKConfig).where(BYOKConfig.installation_id == installation_id)
    )
    return result.scalar_one_or_none()


def decrypt_byok_key(byok_config: BYOKConfig, fernet_key: str) -> str:
    """Decrypt the stored BYOK API key."""
    try:
        return fernet_decrypt(byok_config.encrypted_api_key, fernet_key)
    except InvalidToken as e:
        raise BYOKKeyInvalidError("Stored API key could not be decrypted") from e


async def delete_byok_config(
    session: AsyncSession, installation_id: uuid.UUID
) -> bool:
    """Hard delete BYOK config for an installation."""
    config = await get_byok_config(session, installation_id)
    if not config:
        return False
    await session.delete(config)
    await session.flush()
    await logger.ainfo("byok_config_deleted", installation_id=str(installation_id))
    return True


# --- Suppression Labels Services ---

LABEL_PATTERN = re.compile(r"^[a-zA-Z0-9\-]+$")


def get_default_suppression_labels() -> list[str]:
    """Return default suppression labels."""
    return ["hotfix", "urgent", "trivial"]


async def update_suppression_labels(
    session: AsyncSession, installation_id: uuid.UUID, labels: list[str]
) -> Installation:
    """Update suppression labels for an installation."""
    if len(labels) > 20:
        raise DomainValidationError("Maximum 20 suppression labels allowed")
    for label in labels:
        if len(label) > 50:
            raise DomainValidationError(
                f"Label '{label}' exceeds maximum length of 50 characters"
            )
        if not LABEL_PATTERN.match(label):
            raise DomainValidationError(
                f"Label '{label}' contains invalid characters. Only alphanumeric and hyphens allowed"
            )

    result = await session.execute(
        select(Installation).where(
            Installation.id == installation_id,
            Installation.deleted_at.is_(None),
        )
    )
    installation = result.scalar_one_or_none()
    if not installation:
        from helprs.core.exceptions import NotFoundError

        raise NotFoundError("Installation not found")

    installation.suppression_labels = labels
    await session.flush()
    await logger.ainfo(
        "suppression_labels_updated",
        installation_id=str(installation_id),
        label_count=len(labels),
    )
    return installation
