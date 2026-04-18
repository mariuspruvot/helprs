"""SQLAdmin views for back-office administration."""

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import BYOKConfig, Installation
from helprs.modules.webhook.models import WebhookEvent


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
    """Simple admin authentication backend for MVP internal use."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        password = form.get("password")
        # Simple env-var-based check for MVP; replace with proper auth later
        from helprs.core.config import get_settings

        settings = get_settings()
        # For MVP: accept any login if ENVIRONMENT is development,
        # otherwise require ADMIN_PASSWORD
        if settings.ENVIRONMENT == "development" or (settings.ADMIN_PASSWORD and password == settings.ADMIN_PASSWORD):
            request.session.update({"authenticated": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("authenticated", False)


def setup_admin(app, engine, secret_key: str) -> Admin:
    """Initialize and mount SQLAdmin at /admin."""
    authentication_backend = AdminAuth(secret_key=secret_key)
    admin = Admin(app, engine, authentication_backend=authentication_backend)
    admin.add_view(GitHubUserAdmin)
    admin.add_view(InstallationAdmin)
    admin.add_view(BYOKConfigAdmin)
    admin.add_view(WebhookEventAdmin)
    return admin
