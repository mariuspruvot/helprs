"""Installation API routes."""

from fastapi import APIRouter, Depends, Request, Response

from helprs.core.dependencies import DbSession, GetSettings, get_current_user
from helprs.core.exceptions import NotFoundError
from helprs.core.middleware import limiter
from helprs.modules.installation.schemas import (
    BYOKConfigResponse,
    BYOKConfigureRequest,
    InstallationDetailResponse,
    InstallationListResponse,
    InstallationResponse,
    PaginatedSessionsResponse,
    SessionSummaryResponse,
    SuppressionLabelsRequest,
    SuppressionLabelsResponse,
)
from helprs.modules.installation.service import (
    configure_byok,
    delete_byok_config,
    get_installation_by_github_id,
    get_installations_for_user,
    get_session_counts_for_installations,
    get_sessions_for_installation,
    update_suppression_labels,
    verify_admin_permission,
)

router = APIRouter(prefix="/installations", tags=["installations"])


def _build_installation_response(installation) -> dict:
    """Build installation response dict with BYOK status."""
    data = {
        "id": installation.id,
        "github_installation_id": installation.github_installation_id,
        "account_login": installation.account_login,
        "account_type": installation.account_type,
        "repository_selection": installation.repository_selection,
        "suspended_at": installation.suspended_at,
        "created_at": installation.created_at,
        "suppression_labels": installation.suppression_labels or [],
        "byok_configured": installation.byok_config is not None,
        "byok_key_hint": installation.byok_config.key_hint if installation.byok_config else None,
        "byok_key_status": installation.byok_config.key_status if installation.byok_config else None,
        "byok_validated_at": installation.byok_config.validated_at if installation.byok_config else None,
    }
    return data


@router.get("", response_model=InstallationListResponse)
@limiter.limit("30/minute")
async def list_installations(
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
):
    """List installations the current user has access to."""
    installations = await get_installations_for_user(session, user, settings)
    # Eagerly load byok_config for each installation to avoid lazy-load crash
    for inst in installations:
        await session.refresh(inst, ["byok_config"])

    # Batch-fetch session counts (single GROUP BY query, no N+1)
    installation_ids = [inst.id for inst in installations]
    count_map = await get_session_counts_for_installations(session, installation_ids)

    items = []
    for inst in installations:
        data = _build_installation_response(inst)
        data["session_count"] = count_map.get(inst.id, 0)
        items.append(InstallationResponse(**data))

    return InstallationListResponse(items=items, total=len(items))


@router.get("/{installation_id}", response_model=InstallationDetailResponse)
@limiter.limit("30/minute")
async def get_installation(
    installation_id: int,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
):
    """Get installation details with BYOK status and suppression labels."""
    installation = await get_installation_by_github_id(session, installation_id)
    if not installation:
        raise NotFoundError("Installation not found")
    await verify_admin_permission(user, installation, settings)
    # Eagerly load byok_config
    await session.refresh(installation, ["byok_config"])
    data = _build_installation_response(installation)
    return InstallationDetailResponse(**data)


@router.post("/{installation_id}/byok", response_model=BYOKConfigResponse)
@limiter.limit("10/minute")
async def post_byok(
    installation_id: int,
    body: BYOKConfigureRequest,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
):
    """Configure BYOK API key for an installation."""
    installation = await get_installation_by_github_id(session, installation_id)
    if not installation:
        raise NotFoundError("Installation not found")
    await verify_admin_permission(user, installation, settings)
    config = await configure_byok(session, installation.id, body.api_key, settings.FERNET_KEY)
    return BYOKConfigResponse.model_validate(config)


@router.delete("/{installation_id}/byok", status_code=204)
@limiter.limit("10/minute")
async def delete_byok(
    installation_id: int,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
):
    """Remove BYOK API key for an installation."""
    installation = await get_installation_by_github_id(session, installation_id)
    if not installation:
        raise NotFoundError("Installation not found")
    await verify_admin_permission(user, installation, settings)
    await delete_byok_config(session, installation.id)
    return Response(status_code=204)


@router.put(
    "/{installation_id}/suppression-labels",
    response_model=SuppressionLabelsResponse,
)
@limiter.limit("10/minute")
async def put_suppression_labels(
    installation_id: int,
    body: SuppressionLabelsRequest,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
):
    """Update suppression labels for an installation."""
    installation = await get_installation_by_github_id(session, installation_id)
    if not installation:
        raise NotFoundError("Installation not found")
    await verify_admin_permission(user, installation, settings)
    updated = await update_suppression_labels(session, installation.id, body.labels)
    return SuppressionLabelsResponse(labels=updated.suppression_labels or [])


@router.get("/{installation_id}/sessions", response_model=PaginatedSessionsResponse)
@limiter.limit("30/minute")
async def list_installation_sessions(
    installation_id: int,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
):
    """List sessions for an installation with pagination."""
    installation = await get_installation_by_github_id(session, installation_id)
    if not installation:
        raise NotFoundError("Installation not found")
    await verify_admin_permission(user, installation, settings)

    if per_page > 100:
        per_page = 100
    if page < 1:
        page = 1

    items, total = await get_sessions_for_installation(
        session,
        installation.id,
        page=page,
        per_page=per_page,
        status_filter=status,
    )
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    return PaginatedSessionsResponse(
        items=[SessionSummaryResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )
