"""Installation use cases: lifecycle, access control, BYOK credentials.

Orchestration only — SQL lives in ``repository``, outbound calls in
``github`` and ``anthropic``.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import Settings
from helprs.core.exceptions import (
    BYOKKeyInvalidError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from helprs.core.security import create_app_jwt, fernet_decrypt, fernet_encrypt
from helprs.modules.installation import anthropic, github, repository
from helprs.modules.installation.github import RUNNER_TOKEN_PERMISSIONS
from helprs.modules.installation.models import BYOKConfig, Installation
from helprs.modules.installation.schemas import InstallationPayload

if TYPE_CHECKING:
    from helprs.modules.container.models import ContainerSession
    from helprs.modules.identity.models import GitHubUser

logger = structlog.get_logger()

_NO_ACCESS = "You do not have access to this installation"
_NO_ADMIN = "You do not have admin access to this installation"
_NO_REPO = "You do not have access to this repository"

__all__ = [
    "RUNNER_TOKEN_PERMISSIONS",
    "configure_byok",
    "create_installation",
    "decrypt_byok_key",
    "delete_byok_config",
    "get_byok_config",
    "get_installation_by_github_id",
    "get_installations_for_user",
    "mint_installation_token",
    "post_pr_comment_with_retry",
    "soft_delete_installation",
    "suspend_installation",
    "unsuspend_installation",
    "update_post_results_setting",
    "update_suppression_labels",
    "verify_admin_permission",
    "verify_installation_access",
    "verify_repo_access",
    "verify_session_access",
]

# Re-exported so callers that only need to post a comment do not have to know
# which boundary module implements it.
post_pr_comment_with_retry = github.post_pr_comment_with_retry


# --- Lifecycle -------------------------------------------------------------


async def create_installation(session: AsyncSession, payload: InstallationPayload) -> Installation:
    """Create an installation from a parsed ``installation.created`` event.

    Takes a validated model rather than a raw webhook body. Parsing external
    JSON is a boundary concern: doing it here turned a GitHub shape change
    into a KeyError in the middle of a use case, and this was the only place
    in the codebase where a use case read an unparsed payload.

    Idempotent: a duplicate delivery, or a concurrent one racing us to the
    unique index, resolves to the existing row.
    """
    github_installation_id = payload.github_installation_id

    existing = await repository.get_by_github_id(session, github_installation_id)
    if existing:
        await logger.ainfo("installation_already_exists", github_installation_id=github_installation_id)
        return existing

    created = await repository.add(
        session,
        Installation(
            github_installation_id=github_installation_id,
            account_login=payload.account.login,
            account_id=payload.account.account_id,
            account_type=payload.account.account_type,
            repository_selection=payload.repository_selection,
            app_slug=payload.app_slug,
            target_type=payload.target_type or "Organization",
            permissions=payload.permissions,
            events=payload.events,
            suspended_at=None,
        ),
    )
    if created is None:
        # Lost the race — the winner's row is the one to use.
        existing = await repository.get_by_github_id(session, github_installation_id)
        if existing is None:
            raise ConflictError(f"Could not persist installation {github_installation_id}")
        return existing

    await logger.ainfo(
        "installation_created",
        github_installation_id=github_installation_id,
        account_login=created.account_login,
    )
    return created


async def get_installation_by_github_id(session: AsyncSession, github_installation_id: int) -> Installation | None:
    """Look up an installation by GitHub id, excluding soft-deleted rows."""
    return await repository.get_by_github_id(session, github_installation_id)


async def _apply_lifecycle_change(
    session: AsyncSession,
    github_installation_id: int,
    *,
    event: str,
    deleted_at: datetime | None = None,
    suspended_at: datetime | None = None,
    clear_suspension: bool = False,
) -> Installation | None:
    installation = await repository.get_by_github_id(session, github_installation_id)
    if not installation:
        return None

    if deleted_at is not None:
        installation.deleted_at = deleted_at
    if suspended_at is not None:
        installation.suspended_at = suspended_at
    if clear_suspension:
        installation.suspended_at = None

    await session.flush()
    await logger.ainfo(event, github_installation_id=github_installation_id)
    return installation


async def soft_delete_installation(session: AsyncSession, github_installation_id: int) -> Installation | None:
    """Mark an installation deleted without dropping its history."""
    return await _apply_lifecycle_change(
        session,
        github_installation_id,
        event="installation_soft_deleted",
        deleted_at=datetime.now(UTC),
    )


async def suspend_installation(session: AsyncSession, github_installation_id: int) -> Installation | None:
    return await _apply_lifecycle_change(
        session,
        github_installation_id,
        event="installation_suspended",
        suspended_at=datetime.now(UTC),
    )


async def unsuspend_installation(session: AsyncSession, github_installation_id: int) -> Installation | None:
    return await _apply_lifecycle_change(
        session,
        github_installation_id,
        event="installation_unsuspended",
        clear_suspension=True,
    )


# --- Tokens ----------------------------------------------------------------


async def mint_installation_token(
    github_installation_id: int,
    settings: Settings,
    *,
    repositories: list[str] | None = None,
    permissions: dict[str, str] | None = None,
) -> str:
    """Mint an installation access token, optionally narrowed to one repo."""
    app_jwt = create_app_jwt(settings.GITHUB_APP_ID, settings.GITHUB_APP_PRIVATE_KEY.get_secret_value())
    token = await github.create_installation_access_token(
        github_installation_id,
        app_jwt,
        repositories=repositories,
        permissions=permissions,
    )
    return token.token


def _user_github_token(user: "GitHubUser", settings: Settings) -> str:
    try:
        return fernet_decrypt(user.github_access_token_enc, settings.FERNET_KEY.get_secret_value())
    except InvalidToken as e:
        raise UnauthorizedError("Stored GitHub token is corrupted") from e


# --- Access control --------------------------------------------------------


async def get_installations_for_user(
    session: AsyncSession,
    user: "GitHubUser",
    settings: Settings,
) -> list[Installation]:
    """Installations the user can see.

    GitHub's ``GET /user/installations`` only works with tokens issued by a
    GitHub App's user-authorization flow; it 403s for our OAuth App tokens
    even when the user owns the install. So access is derived locally: User
    installs match on account id, Org installs on membership from
    ``GET /user/orgs`` — a call skipped entirely when no Org install exists.
    """
    org_logins: set[str] = set()
    if await repository.has_organization_installs(session):
        org_logins = await github.fetch_user_org_logins(_user_github_token(user, settings))

    return await repository.list_visible_to(
        session,
        user_github_id=user.github_id,
        org_logins=org_logins,
    )


async def verify_installation_access(user: "GitHubUser", installation: Installation, settings: Settings) -> bool:
    """Member-level access: owner of a User install, or member of the org."""
    if installation.account_type == "User":
        if user.github_id == installation.account_id:
            return True
        raise ForbiddenError(_NO_ACCESS)

    org_logins = await github.fetch_user_org_logins(_user_github_token(user, settings))
    if installation.account_login.lower() in org_logins:
        return True
    raise ForbiddenError(_NO_ACCESS)


async def verify_admin_permission(user: "GitHubUser", installation: Installation, settings: Settings) -> bool:
    """Admin-level access: owner of a User install, or active org admin."""
    token = _user_github_token(user, settings)

    if installation.account_type == "User":
        if user.github_id == installation.account_id:
            return True
        raise ForbiddenError(_NO_ADMIN)

    membership = await github.fetch_org_membership(
        installation.account_login,
        user.github_login,
        token,
        denial=_NO_ADMIN,
    )
    if not membership.is_active_admin:
        raise ForbiddenError(_NO_ADMIN)
    return True


async def verify_repo_access(user: "GitHubUser", repo_full_name: str, settings: Settings) -> bool:
    """Verify the caller can read ``owner/repo`` with their own GitHub token.

    Installation-level access is not enough: an installation may cover repos
    the caller cannot read, and a session clones the repo and streams its diff
    back to that caller.
    """
    await github.assert_repo_visible(repo_full_name, _user_github_token(user, settings), denial=_NO_REPO)
    return True


async def verify_session_access(
    user: "GitHubUser",
    container_session: "ContainerSession",
    db: AsyncSession,
    settings: Settings,
) -> bool:
    """Session owners get in without a GitHub round-trip; others must be members."""
    if container_session.user_id is not None and container_session.user_id == user.id:
        return True

    installation = await repository.get_by_id(db, container_session.installation_id)
    if not installation:
        raise ForbiddenError("Installation not found or deleted")

    return await verify_installation_access(user, installation, settings)


# --- BYOK credentials ------------------------------------------------------


async def configure_byok(
    session: AsyncSession,
    installation_id: uuid.UUID,
    api_key: str,
    fernet_key: str,
) -> BYOKConfig:
    """Validate a Claude credential, then store it encrypted."""
    if not await anthropic.is_credential_valid(api_key):
        raise BYOKKeyInvalidError("API key validation failed -- check your key and try again")

    encrypted_key = fernet_encrypt(api_key, fernet_key)
    key_hint = f"...{api_key[-4:]}"
    now = datetime.now(UTC)

    existing = await repository.get_byok_config(session, installation_id)
    if existing:
        existing.encrypted_api_key = encrypted_key
        existing.key_status = "valid"
        existing.validated_at = now
        existing.key_hint = key_hint
        await session.flush()
        await logger.ainfo("byok_config_updated", installation_id=str(installation_id))
        return existing

    config = await repository.add_byok_config(
        session,
        BYOKConfig(
            installation_id=installation_id,
            encrypted_api_key=encrypted_key,
            key_status="valid",
            validated_at=now,
            key_hint=key_hint,
        ),
    )
    await logger.ainfo("byok_config_created", installation_id=str(installation_id))
    return config


async def get_byok_config(session: AsyncSession, installation_id: uuid.UUID) -> BYOKConfig | None:
    return await repository.get_byok_config(session, installation_id)


def decrypt_byok_key(byok_config: BYOKConfig, fernet_key: str) -> str:
    """Decrypt the stored Claude credential."""
    try:
        return fernet_decrypt(byok_config.encrypted_api_key, fernet_key)
    except InvalidToken as e:
        raise BYOKKeyInvalidError("Stored API key could not be decrypted") from e


async def delete_byok_config(session: AsyncSession, installation_id: uuid.UUID) -> bool:
    config = await repository.get_byok_config(session, installation_id)
    if not config:
        return False
    await repository.delete_byok_config(session, config)
    await logger.ainfo("byok_config_deleted", installation_id=str(installation_id))
    return True


# --- Settings --------------------------------------------------------------


async def _get_active_or_404(session: AsyncSession, installation_id: uuid.UUID) -> Installation:
    installation = await repository.get_by_id(session, installation_id)
    if not installation:
        raise NotFoundError("Installation not found")
    return installation


async def update_suppression_labels(
    session: AsyncSession,
    installation_id: uuid.UUID,
    labels: list[str],
) -> Installation:
    """Set the labels that suppress session creation.

    The label rules (count, length, charset) are enforced by
    ``SuppressionLabelsRequest``, which runs before any handler is entered.
    """
    installation = await _get_active_or_404(session, installation_id)
    installation.suppression_labels = labels
    await session.flush()
    await logger.ainfo(
        "suppression_labels_updated",
        installation_id=str(installation_id),
        label_count=len(labels),
    )
    return installation


async def update_post_results_setting(
    session: AsyncSession,
    installation_id: uuid.UUID,
    enabled: bool,
) -> Installation:
    """Enable or disable posting session results back to the PR."""
    installation = await _get_active_or_404(session, installation_id)
    installation.post_results_to_pr = enabled
    await session.flush()
    await logger.ainfo(
        "post_results_setting_updated",
        installation_id=str(installation_id),
        enabled=enabled,
    )
    return installation
