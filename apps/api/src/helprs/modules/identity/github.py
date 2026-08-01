"""Typed boundary to GitHub's OAuth and user APIs.

Every GitHub response is parsed into a model here, so a shape change surfaces
as a validation error at the edge instead of a ``KeyError`` deep in a service.
Nothing downstream of this module handles raw JSON.
"""

import httpx
from pydantic import BaseModel, Field, ValidationError

from helprs.core.config import Settings
from helprs.core.exceptions import ExternalServiceError, UnauthorizedError

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

_TIMEOUT_SECONDS = 10.0


class GitHubOAuthToken(BaseModel):
    """The credential GitHub hands back for an authorization code."""

    access_token: str
    token_type: str = "bearer"
    scope: str = ""


class GitHubUserProfile(BaseModel):
    """The subset of GitHub's user payload the application stores."""

    github_id: int = Field(alias="id")
    login: str
    email: str | None = None
    avatar_url: str | None = None


def _parse[ModelT: BaseModel](model: type[ModelT], payload: object, what: str) -> ModelT:
    try:
        return model.model_validate(payload)
    except ValidationError as e:
        raise ExternalServiceError(f"Unexpected {what} payload from GitHub") from e


async def exchange_code_for_token(code: str, settings: Settings) -> GitHubOAuthToken:
    """Exchange an OAuth authorization code for a user access token."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET.get_secret_value(),
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        raise ExternalServiceError("GitHub token exchange failed") from e

    payload = resp.json()
    # GitHub answers 200 with an ``error`` key for a bad or expired code.
    if isinstance(payload, dict) and "error" in payload:
        raise UnauthorizedError(f"GitHub OAuth error: {payload['error']}")

    return _parse(GitHubOAuthToken, payload, "OAuth token")


async def fetch_user_profile(access_token: str) -> GitHubUserProfile:
    """Fetch the profile of the user owning ``access_token``."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
    except httpx.TimeoutException as e:
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise UnauthorizedError("GitHub token is invalid or revoked") from e
        raise ExternalServiceError("GitHub API error") from e

    return _parse(GitHubUserProfile, resp.json(), "user")
