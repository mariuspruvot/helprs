"""SQLAdmin views for back-office administration."""

import secrets

import structlog
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from helprs.core.config import get_settings
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import BYOKConfig, Installation
from helprs.modules.webhook.models import WebhookEvent

logger = structlog.get_logger()


class GitHubUserAdmin(ModelView, model=GitHubUser):
    column_list = [
        GitHubUser.id,
        GitHubUser.github_id,
        GitHubUser.github_login,
        GitHubUser.email,
        GitHubUser.created_at,
    ]
    column_searchable_list = [GitHubUser.github_login, GitHubUser.email]
    column_sortable_list = [GitHubUser.github_id, GitHubUser.github_login, GitHubUser.created_at]
    column_details_exclude_list = [GitHubUser.github_access_token_enc]
    # Encrypted credentials must never reach an editable form field.
    form_excluded_columns = [GitHubUser.github_access_token_enc]
    name = "GitHub User"
    name_plural = "GitHub Users"
    icon = "fa-solid fa-users"


class InstallationAdmin(ModelView, model=Installation):
    column_list = [
        Installation.id,
        Installation.github_installation_id,
        Installation.account_login,
        Installation.account_type,
        Installation.repository_selection,
        Installation.post_results_to_pr,
        Installation.suspended_at,
        Installation.deleted_at,
        Installation.created_at,
    ]
    column_searchable_list = [Installation.account_login]
    column_sortable_list = [
        Installation.github_installation_id,
        Installation.account_login,
        Installation.created_at,
    ]
    name = "Installation"
    name_plural = "Installations"
    icon = "fa-solid fa-plug"


class BYOKConfigAdmin(ModelView, model=BYOKConfig):
    column_list = [
        BYOKConfig.id,
        BYOKConfig.installation_id,
        BYOKConfig.key_status,
        BYOKConfig.key_hint,
        BYOKConfig.validated_at,
        BYOKConfig.created_at,
    ]
    column_details_exclude_list = [BYOKConfig.encrypted_api_key]
    # Ciphertext is written only by the BYOK flow, which validates the key
    # first; an operator editing it here could only corrupt the credential.
    form_excluded_columns = [BYOKConfig.encrypted_api_key]
    can_edit = False
    name = "BYOK Config"
    name_plural = "BYOK Configs"
    icon = "fa-solid fa-key"


class WebhookEventAdmin(ModelView, model=WebhookEvent):
    column_list = [
        WebhookEvent.delivery_id,
        WebhookEvent.event_type,
        WebhookEvent.action,
        WebhookEvent.status,
        WebhookEvent.created_at,
    ]
    column_sortable_list = [WebhookEvent.created_at, WebhookEvent.status]
    column_default_sort = ("created_at", True)
    # Read-only — webhook events are managed by the system, never by operators.
    can_create = False
    can_edit = False
    can_delete = False
    name = "Webhook Event"
    name_plural = "Webhook Events"
    icon = "fa-solid fa-bolt"


class AdminAuth(AuthenticationBackend):
    """Password authentication for the admin panel.

    Compared with ``secrets.compare_digest`` so a wrong guess costs the same
    time regardless of how many leading characters matched. There is
    deliberately no environment-based bypass: the panel exposes user rows and
    BYOK ciphertext, so an unset ``ADMIN_PASSWORD`` locks it rather than
    opening it (``setup_admin`` refuses to mount in that case).
    """

    async def login(self, request: Request) -> bool:
        form = await request.form()
        password = form.get("password")
        if not isinstance(password, str):
            return False

        # compare_digest("", "") is True, so an unset password would otherwise
        # authenticate an empty form field.
        expected = get_settings().ADMIN_PASSWORD
        if not expected or not secrets.compare_digest(password, expected):
            return False

        request.session.update({"authenticated": True})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("authenticated", False)


def setup_admin(app, engine, secret_key: str) -> Admin | None:
    """Mount SQLAdmin at /admin, or nothing at all when no password is set."""
    if not get_settings().ADMIN_PASSWORD:
        logger.warning("admin_panel_disabled", reason="ADMIN_PASSWORD is not set")
        return None

    authentication_backend = AdminAuth(secret_key=secret_key)
    admin = Admin(app, engine, authentication_backend=authentication_backend)
    admin.add_view(GitHubUserAdmin)
    admin.add_view(InstallationAdmin)
    admin.add_view(BYOKConfigAdmin)
    admin.add_view(WebhookEventAdmin)
    return admin
