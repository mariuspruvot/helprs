"""Typed boundary to the GitHub App and REST APIs.

Every response is parsed into a model, so a shape change fails here rather
than as a ``KeyError`` inside a use case. Callers above never see raw JSON.
"""

import asyncio
import random

import httpx
from pydantic import BaseModel, ValidationError

from helprs.core.exceptions import (
    DomainValidationError,
    ExternalServiceError,
    ForbiddenError,
    UnauthorizedError,
)

GITHUB_API_BASE = "https://api.github.com"

_TIMEOUT_SECONDS = 10.0
_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# A runner container executes Claude Code over attacker-controllable PR content
# with network egress, so its token is narrowed to the single repo under review
# and to read-only scopes. The API mints its own separate token to write.
RUNNER_TOKEN_PERMISSIONS = {
    "contents": "read",
    "metadata": "read",
    "pull_requests": "read",
}

# Two sleeps for three attempts: after the 1st and 2nd failure, never after
# the last one (it would just hold the caller open for nothing).
_PR_COMMENT_RETRY_DELAYS: tuple[float, ...] = (0.5, 1.0)
_PR_COMMENT_ATTEMPTS = 3
_PR_COMMENT_JITTER = 0.25


class InstallationToken(BaseModel):
    """A GitHub App installation access token, as minted for one installation."""

    token: str
    expires_at: str | None = None


class OrgMembership(BaseModel):
    """A user's membership in an organization."""

    role: str
    state: str

    @property
    def is_active_admin(self) -> bool:
        return self.role == "admin" and self.state == "active"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **_API_HEADERS}


def _translate_status_error(exc: httpx.HTTPStatusError, *, forbidden_message: str | None = None) -> Exception:
    """Map a GitHub HTTP error onto a domain error.

    GitHub answers 404 rather than 403 for resources a token cannot see, so
    both map to the same "no access" outcome when a caller supplies
    ``forbidden_message``.
    """
    status = exc.response.status_code
    if status == 401:
        return UnauthorizedError("GitHub token is invalid or revoked")
    if forbidden_message and status in (403, 404):
        return ForbiddenError(forbidden_message)
    return ExternalServiceError(f"GitHub API error: {status}")


async def _get_json(url: str, token: str, *, forbidden_message: str | None = None) -> object:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=_bearer(token))
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        raise _translate_status_error(e, forbidden_message=forbidden_message) from e
    return resp.json()


async def create_installation_access_token(
    installation_id: int,
    app_jwt: str,
    *,
    repositories: list[str] | None = None,
    permissions: dict[str, str] | None = None,
) -> InstallationToken:
    """Exchange an App JWT for an installation access token.

    Without ``repositories``/``permissions`` GitHub returns a token carrying
    every permission the App holds on every repo in the installation. Callers
    handing the token to a less-trusted consumer must narrow it.
    """
    payload: dict[str, object] = {}
    if repositories is not None:
        payload["repositories"] = repositories
    if permissions is not None:
        payload["permissions"] = permissions

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens",
                headers={"Authorization": f"Bearer {app_jwt}", **_API_HEADERS},
                json=payload or None,
            )
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise UnauthorizedError("GitHub App JWT is invalid or expired") from e
        if e.response.status_code == 422:
            raise DomainValidationError("Requested repository is not covered by this installation") from e
        raise ExternalServiceError(f"GitHub API error: {e.response.status_code}") from e

    try:
        return InstallationToken.model_validate(resp.json())
    except ValidationError as e:
        raise ExternalServiceError("Unexpected installation token payload from GitHub") from e


async def fetch_user_org_logins(user_token: str) -> set[str]:
    """Organizations the token's owner belongs to, lowercased.

    Requires the ``read:org`` scope on the OAuth App.
    """
    payload = await _get_json(f"{GITHUB_API_BASE}/user/orgs", user_token)
    if not isinstance(payload, list):
        raise ExternalServiceError("Unexpected organization list payload from GitHub")
    return {org["login"].lower() for org in payload if isinstance(org, dict) and org.get("login")}


async def fetch_org_membership(org_login: str, username: str, user_token: str, *, denial: str) -> OrgMembership:
    """The caller's membership record in ``org_login``."""
    payload = await _get_json(
        f"{GITHUB_API_BASE}/orgs/{org_login}/memberships/{username}",
        user_token,
        forbidden_message=denial,
    )
    try:
        return OrgMembership.model_validate(payload)
    except ValidationError as e:
        raise ExternalServiceError("Unexpected membership payload from GitHub") from e


async def assert_repo_visible(repo_full_name: str, user_token: str, *, denial: str) -> None:
    """Raise ``ForbiddenError`` unless the token can read ``owner/repo``."""
    await _get_json(f"{GITHUB_API_BASE}/repos/{repo_full_name}", user_token, forbidden_message=denial)


async def post_pr_comment(
    *,
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    installation_token: str,
) -> None:
    """Post a discussion comment on a pull request.

    Uses ``/issues/{n}/comments``: PRs are issues in GitHub's data model, and
    that is the endpoint for general PR discussion — not ``/pulls/{n}/reviews``
    (review submissions) nor ``/pulls/{n}/comments`` (inline code comments).
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments",
            json={"body": body},
            headers=_bearer(installation_token),
        )
        resp.raise_for_status()


async def post_pr_comment_with_retry(
    *,
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    installation_token: str,
) -> None:
    """Post a PR comment, retrying only what is worth retrying.

    5xx and transport errors get three attempts with jittered backoff; 4xx
    (deleted PR, revoked permission, expired token) is permanent for this
    invocation and surfaces immediately. Each attempt uses a fresh client so a
    poisoned connection pool cannot bleed into the next one.
    """
    last_exc: Exception | None = None
    for attempt in range(_PR_COMMENT_ATTEMPTS):
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
            if exc.response.status_code < 500:
                raise ExternalServiceError(
                    f"GitHub rejected PR comment post with HTTP {exc.response.status_code}"
                ) from exc
            last_exc = exc
        except httpx.TransportError as exc:
            last_exc = exc

        if attempt < len(_PR_COMMENT_RETRY_DELAYS):
            await asyncio.sleep(_PR_COMMENT_RETRY_DELAYS[attempt] + random.uniform(0, _PR_COMMENT_JITTER))

    raise ExternalServiceError(f"Failed to post PR comment after {_PR_COMMENT_ATTEMPTS} attempts") from last_exc
