"""Tests for the typed GitHub boundary of the installation module.

Requests go through ``httpx.MockTransport``, so these exercise real request
building — assertions are on the URL, headers and body actually sent.
"""

import httpx
import pytest

from helprs.core.exceptions import (
    DomainValidationError,
    ExternalServiceError,
    ForbiddenError,
    UnauthorizedError,
)
from helprs.modules.installation.github import (
    InstallationToken,
    OrgMembership,
    assert_repo_visible,
    create_installation_access_token,
    fetch_org_membership,
    fetch_user_org_logins,
    post_pr_comment,
    post_pr_comment_with_retry,
)


def _serving(handler, monkeypatch) -> list[httpx.Request]:
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


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch):
    """Retry backoff must not slow the suite down."""

    async def _instant(_seconds):
        return None

    monkeypatch.setattr("helprs.modules.installation.github.asyncio.sleep", _instant)


class TestCreateInstallationAccessToken:
    async def test_returns_typed_token_and_authenticates_with_the_app_jwt(self, monkeypatch):
        seen = _serving(
            lambda _: httpx.Response(201, json={"token": "ghs_abc", "expires_at": "2026-01-01"}), monkeypatch
        )

        token = await create_installation_access_token(123, "app-jwt")

        assert isinstance(token, InstallationToken)
        assert token.token == "ghs_abc"
        assert seen[0].url.path == "/app/installations/123/access_tokens"
        assert seen[0].headers["Authorization"] == "Bearer app-jwt"

    async def test_expired_jwt_is_unauthorized(self, monkeypatch):
        _serving(lambda _: httpx.Response(401), monkeypatch)

        with pytest.raises(UnauthorizedError, match="JWT is invalid or expired"):
            await create_installation_access_token(123, "stale-jwt")

    async def test_unexpected_payload_is_rejected(self, monkeypatch):
        _serving(lambda _: httpx.Response(201, json={"no_token_here": True}), monkeypatch)

        with pytest.raises(ExternalServiceError, match="Unexpected installation token payload"):
            await create_installation_access_token(123, "app-jwt")


class TestFetchUserOrgLogins:
    async def test_lowercases_logins(self, monkeypatch):
        _serving(lambda _: httpx.Response(200, json=[{"login": "Acme"}, {"login": "OTHER"}]), monkeypatch)

        assert await fetch_user_org_logins("gho_token") == {"acme", "other"}

    async def test_ignores_malformed_entries(self, monkeypatch):
        _serving(lambda _: httpx.Response(200, json=[{"login": "acme"}, {}, "junk"]), monkeypatch)

        assert await fetch_user_org_logins("gho_token") == {"acme"}

    async def test_non_list_payload_is_rejected(self, monkeypatch):
        _serving(lambda _: httpx.Response(200, json={"unexpected": "object"}), monkeypatch)

        with pytest.raises(ExternalServiceError, match="Unexpected organization list"):
            await fetch_user_org_logins("gho_token")

    async def test_revoked_token_is_unauthorized(self, monkeypatch):
        _serving(lambda _: httpx.Response(401), monkeypatch)

        with pytest.raises(UnauthorizedError):
            await fetch_user_org_logins("gho_token")


class TestFetchOrgMembership:
    async def test_active_admin(self, monkeypatch):
        _serving(lambda _: httpx.Response(200, json={"role": "admin", "state": "active"}), monkeypatch)

        membership = await fetch_org_membership("acme", "octocat", "gho_token", denial="nope")

        assert isinstance(membership, OrgMembership)
        assert membership.is_active_admin is True

    @pytest.mark.parametrize(
        ("role", "state"),
        [("member", "active"), ("admin", "pending")],
    )
    async def test_not_an_active_admin(self, monkeypatch, role, state):
        _serving(lambda _: httpx.Response(200, json={"role": role, "state": state}), monkeypatch)

        membership = await fetch_org_membership("acme", "octocat", "gho_token", denial="nope")

        assert membership.is_active_admin is False

    @pytest.mark.parametrize("status", [403, 404])
    async def test_invisible_membership_uses_the_caller_message(self, monkeypatch, status):
        _serving(lambda _: httpx.Response(status), monkeypatch)

        with pytest.raises(ForbiddenError, match="no admin access here"):
            await fetch_org_membership("acme", "octocat", "gho_token", denial="no admin access here")


class TestAssertRepoVisible:
    async def test_visible_repo_passes(self, monkeypatch):
        seen = _serving(lambda _: httpx.Response(200, json={"full_name": "acme/api"}), monkeypatch)

        await assert_repo_visible("acme/api", "gho_token", denial="denied")

        assert seen[0].url.path == "/repos/acme/api"

    @pytest.mark.parametrize("status", [403, 404])
    async def test_invisible_repo_is_forbidden(self, monkeypatch, status):
        """GitHub answers 404 for repos a token cannot see; both mean no access."""
        _serving(lambda _: httpx.Response(status), monkeypatch)

        with pytest.raises(ForbiddenError, match="denied"):
            await assert_repo_visible("acme/secret", "gho_token", denial="denied")


class TestPostPRComment:
    async def test_posts_to_the_issues_endpoint(self, monkeypatch):
        seen = _serving(lambda _: httpx.Response(201, json={"id": 1}), monkeypatch)

        await post_pr_comment(owner="acme", repo="api", pr_number=42, body="hi", installation_token="ghs_t")

        assert seen[0].url.path == "/repos/acme/api/issues/42/comments"
        assert seen[0].headers["Authorization"] == "Bearer ghs_t"
        assert b'"body":"hi"' in seen[0].content.replace(b" ", b"")


class TestPostPRCommentWithRetry:
    async def test_retries_a_500_then_succeeds(self, monkeypatch):
        attempts = {"n": 0}

        def _flaky(_request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            return httpx.Response(500) if attempts["n"] == 1 else httpx.Response(201, json={"id": 1})

        _serving(_flaky, monkeypatch)

        await post_pr_comment_with_retry(owner="acme", repo="api", pr_number=1, body="b", installation_token="ghs_t")

        assert attempts["n"] == 2

    async def test_retries_transport_errors(self, monkeypatch):
        attempts = {"n": 0}

        def _flaky(request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise httpx.ConnectError("boom", request=request)
            return httpx.Response(201, json={"id": 1})

        _serving(_flaky, monkeypatch)

        await post_pr_comment_with_retry(owner="acme", repo="api", pr_number=1, body="b", installation_token="ghs_t")

        assert attempts["n"] == 2

    async def test_does_not_retry_a_404(self, monkeypatch):
        """A deleted PR will never succeed — retrying only wastes the budget."""
        attempts = {"n": 0}

        def _gone(_request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            return httpx.Response(404)

        _serving(_gone, monkeypatch)

        with pytest.raises(ExternalServiceError, match="HTTP 404"):
            await post_pr_comment_with_retry(
                owner="acme", repo="api", pr_number=1, body="b", installation_token="ghs_t"
            )

        assert attempts["n"] == 1

    async def test_gives_up_after_three_attempts(self, monkeypatch):
        attempts = {"n": 0}

        def _always_500(_request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            return httpx.Response(503)

        _serving(_always_500, monkeypatch)

        with pytest.raises(ExternalServiceError, match="after 3 attempts"):
            await post_pr_comment_with_retry(
                owner="acme", repo="api", pr_number=1, body="b", installation_token="ghs_t"
            )

        assert attempts["n"] == 3


class TestTokenScoping:
    async def test_runner_token_is_narrowed_to_one_repo_read_only(self, monkeypatch):
        import json

        from helprs.modules.installation.github import RUNNER_TOKEN_PERMISSIONS

        seen = _serving(lambda _: httpx.Response(201, json={"token": "ghs_scoped"}), monkeypatch)

        await create_installation_access_token(7, "app-jwt", repositories=["api"], permissions=RUNNER_TOKEN_PERMISSIONS)

        body = json.loads(seen[0].content)
        assert body["repositories"] == ["api"]
        assert set(body["permissions"].values()) == {"read"}

    async def test_unscoped_request_sends_no_body(self, monkeypatch):
        seen = _serving(lambda _: httpx.Response(201, json={"token": "ghs_full"}), monkeypatch)

        await create_installation_access_token(7, "app-jwt")

        assert seen[0].content in (b"", b"null")

    async def test_repo_outside_installation_is_rejected(self, monkeypatch):
        _serving(lambda _: httpx.Response(422), monkeypatch)

        with pytest.raises(DomainValidationError, match="not covered by this installation"):
            await create_installation_access_token(7, "app-jwt", repositories=["not-mine"])
