"""Tests for admin panel authentication.

The panel exposes user rows and BYOK ciphertext, so the login path is
security-critical: it previously accepted any password whenever ENVIRONMENT
was "development" — which is the default value.
"""

import pytest

from helprs.admin.views import AdminAuth, BYOKConfigAdmin, GitHubUserAdmin, setup_admin
from helprs.core.config import Settings, get_settings


class FakeFormRequest:
    """Minimal Request stand-in exposing the two attributes login() touches."""

    def __init__(self, form_data: dict[str, object]) -> None:
        self._form = form_data
        self.session: dict[str, object] = {}

    async def form(self) -> dict[str, object]:
        return self._form


@pytest.fixture
def admin_settings(monkeypatch):
    """Point get_settings() at a config with a known admin password."""

    def _apply(**overrides) -> Settings:
        settings = get_settings().model_copy(update=overrides)
        monkeypatch.setattr("helprs.admin.views.get_settings", lambda: settings)
        return settings

    return _apply


async def test_correct_password_authenticates(admin_settings):
    admin_settings(ADMIN_PASSWORD="s3cret", ENVIRONMENT="production")
    request = FakeFormRequest({"password": "s3cret"})

    assert await AdminAuth(secret_key="k").login(request) is True
    assert request.session == {"authenticated": True}


async def test_wrong_password_is_rejected(admin_settings):
    admin_settings(ADMIN_PASSWORD="s3cret", ENVIRONMENT="production")
    request = FakeFormRequest({"password": "wrong"})

    assert await AdminAuth(secret_key="k").login(request) is False
    assert request.session == {}


async def test_development_environment_does_not_bypass_the_password(admin_settings):
    """Regression: ENVIRONMENT is "development" by default, so a bypass there
    means an unauthenticated /admin on any deploy that forgets the variable."""
    admin_settings(ADMIN_PASSWORD="s3cret", ENVIRONMENT="development")
    request = FakeFormRequest({"password": "anything"})

    assert await AdminAuth(secret_key="k").login(request) is False
    assert request.session == {}


async def test_empty_password_is_rejected_when_none_configured(admin_settings):
    admin_settings(ADMIN_PASSWORD="", ENVIRONMENT="development")

    assert await AdminAuth(secret_key="k").login(FakeFormRequest({"password": ""})) is False


async def test_missing_password_field_is_rejected(admin_settings):
    admin_settings(ADMIN_PASSWORD="s3cret", ENVIRONMENT="production")

    assert await AdminAuth(secret_key="k").login(FakeFormRequest({})) is False


async def test_authenticate_follows_the_session_flag():
    backend = AdminAuth(secret_key="k")
    authenticated = FakeFormRequest({})
    authenticated.session["authenticated"] = True

    assert await backend.authenticate(authenticated) is True
    assert await backend.authenticate(FakeFormRequest({})) is False


async def test_logout_clears_the_session():
    request = FakeFormRequest({})
    request.session["authenticated"] = True

    assert await AdminAuth(secret_key="k").logout(request) is True
    assert request.session == {}


def test_panel_is_not_mounted_without_a_password(monkeypatch):
    settings = get_settings().model_copy(update={"ADMIN_PASSWORD": ""})
    monkeypatch.setattr("helprs.admin.views.get_settings", lambda: settings)

    assert setup_admin(app=None, engine=None, secret_key="k") is None


def test_credential_columns_are_excluded_from_edit_forms():
    """Ciphertext must be unreachable from the admin forms, not just hidden
    on the detail page."""
    assert BYOKConfigAdmin.can_edit is False
    assert "encrypted_api_key" in {c.key for c in BYOKConfigAdmin.form_excluded_columns}
    assert "github_access_token_enc" in {c.key for c in GitHubUserAdmin.form_excluded_columns}
