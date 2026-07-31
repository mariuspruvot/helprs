"""Identity API routes.

Handlers stay thin: validate the request, call one service use case, shape the
response. Cookie policy lives here because it is transport, not domain.
"""

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from helprs.core.config import Settings
from helprs.core.dependencies import CurrentUser, DbSession, GetSettings
from helprs.core.exceptions import UnauthorizedError
from helprs.core.middleware import limiter
from helprs.modules.identity.schemas import TokenResponse, UserResponse, UserStatsResponse
from helprs.modules.identity.service import authenticate_with_code, get_user_stats, refresh_tokens

router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
# ``read:org`` is required so ``get_installations_for_user`` can call
# ``GET /user/orgs`` to verify membership for Org-type installs. User-type
# installs do not need it.
OAUTH_SCOPES = "read:user,user:email,read:org"

_OAUTH_STATE_COOKIE = "oauth_state"
_REFRESH_COOKIE = "refresh_token"
_OAUTH_STATE_MAX_AGE = 600
_REFRESH_MAX_AGE = 7 * 24 * 3600


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        _REFRESH_COOKIE,
        token,
        httponly=True,
        secure=settings.ENVIRONMENT != "development",
        samesite="lax",
        max_age=_REFRESH_MAX_AGE,
    )


@router.get("/github")
@limiter.limit("10/minute")
async def github_login(request: Request, settings: GetSettings) -> RedirectResponse:
    """Redirect to GitHub's authorization page, remembering a CSRF state."""
    state = secrets.token_urlsafe(32)
    params = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            "scope": OAUTH_SCOPES,
            "state": state,
        }
    )
    response = RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{params}")
    response.set_cookie(
        _OAUTH_STATE_COOKIE,
        state,
        httponly=True,
        secure=settings.ENVIRONMENT != "development",
        samesite="lax",
        max_age=_OAUTH_STATE_MAX_AGE,
    )
    return response


def _verify_oauth_state(request: Request, state: str | None, installation_id: int | None) -> None:
    """Two flows land on the callback: an OAuth login carries ``state``, a
    GitHub App installation redirect carries ``installation_id`` instead."""
    if state is not None:
        stored = request.cookies.get(_OAUTH_STATE_COOKIE)
        if not stored or not secrets.compare_digest(stored, state):
            raise UnauthorizedError("Invalid OAuth state parameter")
        return
    if installation_id is None:
        raise UnauthorizedError("Missing OAuth state parameter")


@router.get("/github/callback")
@limiter.limit("10/minute")
async def github_callback(
    request: Request,
    code: str,
    session: DbSession,
    settings: GetSettings,
    state: str | None = None,
    installation_id: int | None = None,
    setup_action: str | None = None,
) -> RedirectResponse:
    """Exchange the authorization code, upsert the user, issue tokens."""
    _verify_oauth_state(request, state, installation_id)

    _, tokens = await authenticate_with_code(session, code, settings)

    response = RedirectResponse(url=f"{settings.APP_BASE_URL}/auth/callback?access_token={tokens.access_token}")
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    response.delete_cookie(_OAUTH_STATE_COOKIE)
    return response


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(request: Request, session: DbSession, settings: GetSettings) -> Response:
    """Trade the httpOnly refresh cookie for a new token pair."""
    refresh_cookie = request.cookies.get(_REFRESH_COOKIE)
    if not refresh_cookie:
        raise UnauthorizedError("Missing refresh token")

    tokens = await refresh_tokens(refresh_cookie, session, settings)

    response = Response(
        content=TokenResponse(access_token=tokens.access_token).model_dump_json(),
        media_type="application/json",
    )
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return response


@router.get("/me/stats", response_model=UserStatsResponse)
@limiter.limit("30/minute")
async def get_my_stats(
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> UserStatsResponse:
    """Session statistics for the authenticated user."""
    return await get_user_stats(session, user, settings)


@router.get("/me", response_model=UserResponse)
@limiter.limit("30/minute")
async def get_me(request: Request, user: CurrentUser) -> UserResponse:
    """Return the current authenticated user."""
    return UserResponse.model_validate(user)


@router.post("/logout")
@limiter.limit("30/minute")
async def logout(request: Request, settings: GetSettings) -> Response:
    """Clear the refresh cookie."""
    response = Response(content='{"status":"ok"}', media_type="application/json")
    # Attributes must match those used to set it, or the browser keeps it.
    response.delete_cookie(
        _REFRESH_COOKIE,
        httponly=True,
        secure=settings.ENVIRONMENT != "development",
        samesite="lax",
    )
    return response
