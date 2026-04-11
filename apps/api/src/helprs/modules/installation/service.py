"""Installation business logic."""

import asyncio
import random
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
from helprs.core.security import create_app_jwt, fernet_decrypt, fernet_encrypt
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
        raise ExternalServiceError(f"GitHub API error: {e.response.status_code}") from e
    return resp.json()


async def mint_installation_token(github_installation_id: int, settings: Settings) -> str:
    """Mint a scoped GitHub App installation access token.

    Thin orchestrator over ``create_app_jwt`` + ``get_installation_access_token``
    that returns the bare token string — callers building an
    ``Authorization: Bearer ...`` header do not need the metadata envelope.
    """
    app_jwt = create_app_jwt(settings.GITHUB_APP_ID, settings.GITHUB_APP_PRIVATE_KEY)
    response = await get_installation_access_token(github_installation_id, app_jwt)
    return response["token"]


async def post_pr_comment(
    *,
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    installation_token: str,
) -> None:
    """Post an issue comment on a pull request via the GitHub REST API.

    Uses the ``/repos/{owner}/{repo}/issues/{pr_number}/comments`` endpoint
    — PRs are issues in GitHub's data model, and that endpoint is the
    correct one for general PR discussion comments (NOT
    ``/pulls/{n}/reviews`` which is for review comments, or
    ``/pulls/{n}/comments`` which is for inline code comments).
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json={"body": body}, headers=headers)
        resp.raise_for_status()


# Inter-attempt sleeps for 3 total attempts — only 2 sleeps are needed
# (after the 1st and 2nd failures). No sleep follows the final failure.
_PR_COMMENT_RETRY_DELAYS: tuple[float, ...] = (0.5, 1.0)


async def post_pr_comment_with_retry(
    *,
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    installation_token: str,
) -> None:
    """Retry wrapper around ``post_pr_comment`` with exponential backoff.

    Policy:
    * 3 attempts total, with 0.5s / 1.0s sleeps between attempts plus up
      to 0.25s jitter. No sleep after the final failure (avoids wasting
      NFR1 budget and holding the outer DB transaction open longer than
      needed).
    * Retries only on ``httpx.TransportError`` and HTTP 5xx responses.
      4xx (deleted PR, permission revoked, expired token) are permanent
      failures for this invocation and are raised immediately.
    * Final failure is wrapped in ``ExternalServiceError`` so the webhook
      background task's ``mark_failed`` path catches it cleanly.

    Uses a fresh ``httpx.AsyncClient`` per attempt (via ``post_pr_comment``)
    so a poisoned connection pool from one failure cannot bleed into the
    next attempt.
    """
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            await post_pr_comment(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                body=body,
                installation_token=installation_token,
            )
            return
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status < 500:
                # 4xx is permanent for this invocation; surface immediately.
                raise ExternalServiceError(f"GitHub rejected PR comment post with HTTP {status}") from exc
            last_exc = exc
        except httpx.TransportError as exc:
            last_exc = exc

        if attempt < len(_PR_COMMENT_RETRY_DELAYS):
            delay = _PR_COMMENT_RETRY_DELAYS[attempt] + random.uniform(0, 0.25)
            await asyncio.sleep(delay)

    raise ExternalServiceError("Failed to post PR comment after 3 attempts") from last_exc


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


async def soft_delete_installation(session: AsyncSession, github_installation_id: int) -> Installation | None:
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


async def suspend_installation(session: AsyncSession, github_installation_id: int) -> Installation | None:
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


async def unsuspend_installation(session: AsyncSession, github_installation_id: int) -> Installation | None:
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


async def get_installation_by_github_id(session: AsyncSession, github_installation_id: int) -> Installation | None:
    """Lookup installation by GitHub ID, excluding soft-deleted records."""
    result = await session.execute(
        select(Installation).where(
            Installation.github_installation_id == github_installation_id,
            Installation.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_installations_for_user(session: AsyncSession, user, settings: Settings) -> list[Installation]:
    """Get installations the user has access to.

    GitHub's ``GET /user/installations`` only works with tokens issued by a
    GitHub App's user-authorization OAuth flow — it 403s for tokens issued
    by a separate OAuth App, even when the user owns the install. We use
    an OAuth App for login (see ``identity/router.py``), so we cannot rely
    on that endpoint. Instead we replicate the access semantics locally:

    * **User-type installs**: the user has access iff
      ``installation.account_id == user.github_id`` (they own the account
      the App is installed on). No outbound call needed.
    * **Org-type installs**: the user has access iff they're a member of
      the org. We check via ``GET /user/orgs`` (requires ``read:org`` scope
      in the OAuth App's authorization). The call is skipped entirely if
      no Org-type installs exist in the DB.

    Discovered as a P0 regression during Story 3-3 manual QA on 2026-04-11
    — Epic 1's ``/user/installations`` design was never end-to-end tested
    because the manual-QA gate had been bypassed for stories 1-3, 1-4,
    and 1-5.
    """
    result = await session.execute(select(Installation).where(Installation.deleted_at.is_(None)))
    all_installs = list(result.scalars().all())
    if not all_installs:
        return []

    user_installs = [i for i in all_installs if i.account_type == "User" and i.account_id == user.github_id]
    org_installs = [i for i in all_installs if i.account_type == "Organization"]

    if not org_installs:
        return user_installs

    try:
        github_token = fernet_decrypt(user.github_access_token_enc, settings.FERNET_KEY)
    except InvalidToken as e:
        raise UnauthorizedError("Stored GitHub token is corrupted") from e

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/user/orgs",
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
        raise ExternalServiceError(f"GitHub API error: {e.response.status_code}") from e

    user_org_logins = {org["login"].lower() for org in resp.json() if isinstance(org, dict) and org.get("login")}
    accessible_org_installs = [i for i in org_installs if i.account_login.lower() in user_org_logins]
    return user_installs + accessible_org_installs


async def verify_admin_permission(user, installation: Installation, settings: Settings) -> bool:
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
            raise ForbiddenError("You do not have admin access to this installation") from e
        raise ExternalServiceError(f"GitHub API error: {e.response.status_code}") from e

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
        raise ExternalServiceError(f"Anthropic API error: {e.response.status_code}") from e
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
        raise BYOKKeyInvalidError("API key validation failed -- check your key and try again")

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


async def get_byok_config(session: AsyncSession, installation_id: uuid.UUID) -> BYOKConfig | None:
    """Get BYOK config for an installation."""
    result = await session.execute(select(BYOKConfig).where(BYOKConfig.installation_id == installation_id))
    return result.scalar_one_or_none()


def decrypt_byok_key(byok_config: BYOKConfig, fernet_key: str) -> str:
    """Decrypt the stored BYOK API key."""
    try:
        return fernet_decrypt(byok_config.encrypted_api_key, fernet_key)
    except InvalidToken as e:
        raise BYOKKeyInvalidError("Stored API key could not be decrypted") from e


async def delete_byok_config(session: AsyncSession, installation_id: uuid.UUID) -> bool:
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
            raise DomainValidationError(f"Label '{label}' exceeds maximum length of 50 characters")
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
