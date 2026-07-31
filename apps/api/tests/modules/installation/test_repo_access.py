"""Tests for per-repo authorization and runner token scoping.

Installation-level access is not enough to start a session: an installation
can cover repos the caller cannot read, and a session clones the repo and
streams its diff back to that caller.
"""

import httpx
import pytest

from helprs.core.config import get_settings
from helprs.core.exceptions import DomainValidationError, ExternalServiceError, ForbiddenError, UnauthorizedError
from helprs.core.security import fernet_encrypt
from helprs.modules.installation.github import (
    RUNNER_TOKEN_PERMISSIONS,
    create_installation_access_token,
)
from helprs.modules.installation.service import verify_repo_access


class FakeUser:
    """The three attributes verify_repo_access reads off a GitHubUser."""

    def __init__(self, token: str = "gho_usertoken") -> None:
        settings = get_settings()
        self.github_access_token_enc = fernet_encrypt(token, settings.FERNET_KEY)
        self.github_id = 4242
        self.github_login = "octocat"


def _route_through(handler, monkeypatch) -> list[httpx.Request]:
    """Serve every outbound httpx call from `handler`, recording requests."""
    seen: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    original = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_record)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)
    return seen


async def test_readable_repo_is_allowed(monkeypatch):
    seen = _route_through(lambda _: httpx.Response(200, json={"full_name": "acme/api"}), monkeypatch)

    assert await verify_repo_access(FakeUser(), "acme/api", get_settings()) is True

    assert str(seen[0].url) == "https://api.github.com/repos/acme/api"
    assert seen[0].headers["Authorization"] == "Bearer gho_usertoken"


@pytest.mark.parametrize("status", [403, 404])
async def test_invisible_repo_is_forbidden(monkeypatch, status):
    """GitHub answers 404 (not 403) for repos a token cannot see; both mean
    the caller has no access."""
    _route_through(lambda _: httpx.Response(status), monkeypatch)

    with pytest.raises(ForbiddenError, match="do not have access to this repository"):
        await verify_repo_access(FakeUser(), "acme/secret", get_settings())


async def test_revoked_user_token_is_unauthorized(monkeypatch):
    _route_through(lambda _: httpx.Response(401), monkeypatch)

    with pytest.raises(UnauthorizedError):
        await verify_repo_access(FakeUser(), "acme/api", get_settings())


async def test_github_outage_surfaces_as_external_error(monkeypatch):
    _route_through(lambda _: httpx.Response(503), monkeypatch)

    with pytest.raises(ExternalServiceError):
        await verify_repo_access(FakeUser(), "acme/api", get_settings())


async def test_corrupted_stored_token_is_unauthorized():
    user = FakeUser()
    user.github_access_token_enc = "not-valid-ciphertext"

    with pytest.raises(UnauthorizedError, match="corrupted"):
        await verify_repo_access(user, "acme/api", get_settings())


async def test_runner_token_request_is_scoped_to_one_repo(monkeypatch):
    """The container gets a token narrowed to the repo under review with
    read-only scopes — it runs Claude Code over untrusted PR content."""
    seen = _route_through(lambda _: httpx.Response(201, json={"token": "ghs_scoped"}), monkeypatch)

    token = await create_installation_access_token(
        123,
        "app-jwt",
        repositories=["api"],
        permissions=RUNNER_TOKEN_PERMISSIONS,
    )

    assert token.token == "ghs_scoped"
    import json

    body = json.loads(seen[0].content)
    assert body["repositories"] == ["api"]
    assert body["permissions"] == {"contents": "read", "metadata": "read", "pull_requests": "read"}
    assert "write" not in str(body["permissions"].values())


async def test_unscoped_token_request_sends_no_body(monkeypatch):
    """The API's own token (used to post PR comments) keeps full installation
    scope, so no narrowing body is sent."""
    seen = _route_through(lambda _: httpx.Response(201, json={"token": "ghs_full"}), monkeypatch)

    await create_installation_access_token(123, "app-jwt")

    assert seen[0].content in (b"", b"null")


async def test_repo_outside_installation_is_rejected(monkeypatch):
    """GitHub replies 422 when asked to scope a token to a repo the
    installation does not cover."""
    _route_through(lambda _: httpx.Response(422), monkeypatch)

    with pytest.raises(DomainValidationError, match="not covered by this installation"):
        await create_installation_access_token(123, "app-jwt", repositories=["not-mine"])
