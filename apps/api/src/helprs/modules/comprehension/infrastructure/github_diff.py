"""Fetch PR diffs from GitHub via installation access token.

Separated from ``installation/service.py`` because diff fetching belongs
to the comprehension read path (not installation configuration). Putting
it here keeps the module-boundary rule clean: ``comprehension`` reuses
``installation.service.mint_installation_token`` (the *application*
surface) without importing anything from ``installation.infrastructure``.

The wrapper is deliberately thin so tests can mock it by patching this
module directly.
"""

from urllib.parse import quote

import httpx

from helprs.core.exceptions import (
    ExternalServiceError,
    NotFoundError,
    RateLimitExceededError,
)

_GITHUB_API_BASE = "https://api.github.com"

# Hard cap on the total byte length of the string we return (body +
# truncation marker). Story 3.5 will replace this naive truncation with
# file-ranked selection for the 2000+-line-PR case; until then a visible
# marker is kinder to the user than a silent 500.
_MAX_DIFF_BYTES = 1_000_000  # 1 MB
_TRUNCATION_MARKER = "\n\n<!-- truncated: diff exceeded 1 MB -->\n"
_MARKER_BYTES = len(_TRUNCATION_MARKER.encode("utf-8"))
# Body capacity leaves room for the marker so the full return value
# stays strictly under ``_MAX_DIFF_BYTES``.
_BODY_BYTE_BUDGET = _MAX_DIFF_BYTES - _MARKER_BYTES


def _scrub_auth(request: httpx.Request | None) -> None:
    """Redact the bearer token from a captured httpx request so any
    downstream exception handler or structured logger that serializes
    ``request.headers`` cannot leak the installation token.
    """
    if request is None:
        return
    try:
        if "authorization" in request.headers:
            request.headers["authorization"] = "Bearer <redacted>"
    except Exception:  # pragma: no cover — defensive only
        pass


async def fetch_pr_diff(
    *,
    owner: str,
    repo: str,
    pr_number: int,
    installation_token: str,
) -> str:
    """Fetch the unified diff for a PR using an installation access token.

    Uses the canonical ``/repos/{owner}/{repo}/pulls/{pr_number}`` REST
    endpoint with ``Accept: application/vnd.github.v3.diff``. We do NOT
    hit the webhook-provided ``pr_diff_url`` (signed S3 URL) — that path
    has historically been flaky for auth-gated private repos.

    The body is streamed chunk-by-chunk and capped at
    ``_BODY_BYTE_BUDGET`` so a pathological upstream response (GB-scale
    monorepo diff) cannot OOM the worker. When the cap is hit, the
    result is truncated and an HTML comment marker is appended; the
    total return size stays at or below ``_MAX_DIFF_BYTES``.

    A fresh ``httpx.AsyncClient`` is opened per call to match the
    Story 2.2 ``post_pr_comment`` pattern (no connection-pool leakage,
    predictable cleanup).
    """
    safe_owner = quote(owner, safe="")
    safe_repo = quote(repo, safe="")
    url = f"{_GITHUB_API_BASE}/repos/{safe_owner}/{safe_repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    buffer = bytearray()
    truncated = False

    try:
        async with (
            httpx.AsyncClient(timeout=10.0) as client,
            client.stream("GET", url, headers=headers) as resp,
        ):
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                remaining = _BODY_BYTE_BUDGET - len(buffer)
                if remaining <= 0:
                    truncated = True
                    break
                if len(chunk) > remaining:
                    buffer.extend(chunk[:remaining])
                    truncated = True
                    break
                buffer.extend(chunk)
    except httpx.TimeoutException as e:
        _scrub_auth(e.request)
        raise ExternalServiceError("GitHub is temporarily unavailable") from e
    except httpx.HTTPStatusError as e:
        _scrub_auth(e.request)
        status = e.response.status_code
        if status == 404:
            raise NotFoundError(f"PR {owner}/{repo}#{pr_number} not found on GitHub") from e
        if status == 429:
            raise RateLimitExceededError("GitHub API rate limit exceeded") from e
        raise ExternalServiceError(f"GitHub API error: {status}") from e
    except httpx.RequestError as e:
        _scrub_auth(e.request)
        raise ExternalServiceError("GitHub is temporarily unavailable") from e

    body = bytes(buffer).decode("utf-8", errors="ignore")
    if truncated:
        return body + _TRUNCATION_MARKER
    return body
