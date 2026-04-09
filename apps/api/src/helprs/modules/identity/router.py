"""Identity API routes."""

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from helprs.core.dependencies import DbSession, GetSettings, get_current_user
from helprs.core.middleware import limiter
from helprs.modules.identity.schemas import TokenResponse, UserResponse
from helprs.modules.identity.service import (
    create_token_pair,
    exchange_code_for_token,
    fetch_github_user,
    get_or_create_user,
    refresh_tokens,
)

router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
OAUTH_SCOPES = "read:user,user:email"


@router.get("/github")
@limiter.limit("10/minute")
async def github_login(request: Request, settings: GetSettings):
    """Redirect to GitHub OAuth authorization page."""
    state = secrets.token_urlsafe(32)
    # Store state in a cookie for CSRF validation on callback
    params = urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "scope": OAUTH_SCOPES,
        "state": state,
    })
    is_secure = settings.ENVIRONMENT != "development"
    response = RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{params}")
    response.set_cookie(
        "oauth_state",
        state,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/github/callback")
@limiter.limit("10/minute")
async def github_callback(
    request: Request,
    code: str,
    state: str,
    session: DbSession,
    settings: GetSettings,
):
    """Handle GitHub OAuth callback: exchange code, create user, issue tokens."""
    # Validate CSRF state
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or not secrets.compare_digest(stored_state, state):
        from helprs.core.exceptions import UnauthorizedError

        raise UnauthorizedError("Invalid OAuth state parameter")

    # Exchange code for GitHub access token
    token_data = await exchange_code_for_token(code, settings)
    github_access_token = token_data["access_token"]

    # Fetch GitHub user profile
    github_user_data = await fetch_github_user(github_access_token)

    # Create or update user record
    user = await get_or_create_user(session, github_user_data, github_access_token, settings)

    # Issue JWT + refresh token
    access_token, refresh_token = create_token_pair(user, settings)

    # Redirect to frontend with access_token, set refresh token as httpOnly cookie
    frontend_url = settings.CORS_ORIGINS[0] if settings.CORS_ORIGINS else "http://localhost:5173"
    redirect_url = f"{frontend_url}/auth/callback?access_token={access_token}"

    is_secure = settings.ENVIRONMENT != "development"
    response = RedirectResponse(url=redirect_url)
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=7 * 24 * 3600,  # 7 days
    )
    response.delete_cookie("oauth_state")
    return response


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    session: DbSession,
    settings: GetSettings,
):
    """Refresh access token using httpOnly refresh cookie."""
    refresh_cookie = request.cookies.get("refresh_token")
    if not refresh_cookie:
        from helprs.core.exceptions import UnauthorizedError

        raise UnauthorizedError("Missing refresh token")

    access_token, new_refresh_token = await refresh_tokens(refresh_cookie, session, settings)

    response = Response(
        content=TokenResponse(access_token=access_token).model_dump_json(),
        media_type="application/json",
    )
    is_secure = settings.ENVIRONMENT != "development"
    response.set_cookie(
        "refresh_token",
        new_refresh_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    return response


@router.get("/me", response_model=UserResponse)
@limiter.limit("30/minute")
async def get_me(
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
):
    """Return the current authenticated user."""
    return user


@router.post("/logout")
async def logout():
    """Clear the refresh token cookie."""
    response = Response(content='{"status":"ok"}', media_type="application/json")
    response.delete_cookie("refresh_token", httponly=True, secure=True, samesite="lax")
    return response
