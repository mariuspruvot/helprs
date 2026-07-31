"""A hand-written GitHub API double.

Replaces per-test ``unittest.mock`` patching of ``httpx.AsyncClient``: routing
on the request URL means one double serves every GitHub call a request makes
(org membership, org list, repo visibility, token minting) instead of
returning one canned payload to all of them.
"""

import contextlib
import json
import re

import httpx

_ORG_MEMBERSHIP = re.compile(r"/orgs/(?P<org>[^/]+)/memberships/")
_REPO = re.compile(r"/repos/(?P<full_name>[^/]+/[^/]+)$")


class GitHubDouble:
    """Serves the GitHub endpoints the installation module talks to.

    Every call is recorded on ``requests`` so tests can assert on what was
    actually sent — URL, headers and body — which patched mocks cannot do.
    """

    def __init__(
        self,
        *,
        org_role: str = "admin",
        org_state: str = "active",
        user_orgs: list[str] | None = None,
        visible_repos: list[str] | None = None,
        installation_token: str = "ghs_test_token",
        claude_key_valid: bool = True,
        fail_comments: bool = False,
    ) -> None:
        self.org_role = org_role
        self.org_state = org_state
        self.user_orgs = user_orgs
        self.visible_repos = visible_repos
        self.installation_token = installation_token
        self.claude_key_valid = claude_key_valid
        self.fail_comments = fail_comments
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path

        # Anthropic: BYOK key validation hits /v1/models.
        if request.url.host == "api.anthropic.com":
            return httpx.Response(200 if self.claude_key_valid else 401, json={})

        if _ORG_MEMBERSHIP.search(path):
            return httpx.Response(200, json={"role": self.org_role, "state": self.org_state})

        if path == "/user/orgs":
            orgs = self.user_orgs if self.user_orgs is not None else ["test-org", "empty-org"]
            return httpx.Response(200, json=[{"login": login} for login in orgs])

        repo_match = _REPO.search(path)
        if repo_match:
            full_name = repo_match.group("full_name")
            if self.visible_repos is None or full_name in self.visible_repos:
                return httpx.Response(200, json={"full_name": full_name})
            return httpx.Response(404, json={"message": "Not Found"})

        if path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": self.installation_token})

        if "/issues/" in path and path.endswith("/comments"):
            if self.fail_comments:
                return httpx.Response(500, json={"message": "GitHub is having a bad day"})
            return httpx.Response(201, json={"id": 1})

        return httpx.Response(404, json={"message": f"Unhandled in double: {path}"})

    def body_of(self, index: int = 0) -> dict:
        """Decode the JSON body of a recorded request."""
        return json.loads(self.requests[index].content or b"{}")


@contextlib.contextmanager
def serving_github(**kwargs):
    """Route every ``httpx.AsyncClient`` call through a ``GitHubDouble``.

    Restores the real client on exit, including when the test body raises.
    """
    double = GitHubDouble(**kwargs)
    original = httpx.AsyncClient

    def _client(*args, **client_kwargs):
        client_kwargs["transport"] = httpx.MockTransport(double.handle)
        return original(*args, **client_kwargs)

    httpx.AsyncClient = _client
    try:
        yield double
    finally:
        httpx.AsyncClient = original
