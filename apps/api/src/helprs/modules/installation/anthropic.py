"""Typed boundary to the Anthropic API, used to validate BYOK credentials."""

import httpx

from helprs.core.exceptions import ExternalServiceError

ANTHROPIC_API_BASE = "https://api.anthropic.com"

_TIMEOUT_SECONDS = 10.0
_OAUTH_TOKEN_PREFIX = "sk-ant-oat"


def is_oauth_token(credential: str) -> bool:
    """Whether the credential is a Claude OAuth token rather than an API key."""
    return credential.startswith(_OAUTH_TOKEN_PREFIX)


async def is_credential_valid(credential: str) -> bool:
    """Check a Claude credential against the Anthropic API.

    OAuth tokens are accepted without a server-side check: the REST API does
    not accept them, so they can only be validated at runtime by the Claude
    Code CLI inside the container.
    """
    if is_oauth_token(credential):
        return True

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{ANTHROPIC_API_BASE}/v1/models",
                headers={"x-api-key": credential, "anthropic-version": "2023-06-01"},
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
