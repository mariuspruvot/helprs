"""Installation API routes.

Handlers resolve the installation, check authorization, call one use case and
shape the response. Two tiers apply: reads need membership, mutations of
credentials and settings need org-admin.
"""

from fastapi import APIRouter, Request, Response

from helprs.core.dependencies import CurrentUser, DbSession, GetSettings
from helprs.core.exceptions import NotFoundError
from helprs.core.middleware import limiter
from helprs.modules.container import repository as sessions
from helprs.modules.container.models import ContainerStatus
from helprs.modules.installation.models import Installation
from helprs.modules.installation.schemas import (
    BYOKConfigResponse,
    BYOKConfigureRequest,
    InstallationDetailResponse,
    InstallationListResponse,
    InstallationResponse,
    PaginatedSessionsResponse,
    PostResultsSettingRequest,
    PostResultsSettingResponse,
    SessionSummaryResponse,
    SuppressionLabelsRequest,
    SuppressionLabelsResponse,
)
from helprs.modules.installation.service import (
    configure_byok,
    delete_byok_config,
    get_installation_by_github_id,
    get_installations_for_user,
    update_post_results_setting,
    update_suppression_labels,
    verify_admin_permission,
    verify_installation_access,
)

router = APIRouter(prefix="/installations", tags=["installations"])

MAX_PAGE_SIZE = 100


async def _installation_or_404(session, github_installation_id: int) -> Installation:
    installation = await get_installation_by_github_id(session, github_installation_id)
    if not installation:
        raise NotFoundError("Installation not found")
    return installation


@router.get("", response_model=InstallationListResponse)
@limiter.limit("30/minute")
async def list_installations(
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> InstallationListResponse:
    """List installations the current user has access to."""
    installations = await get_installations_for_user(session, user, settings)
    counts = await sessions.count_grouped_by_installation(session, [i.id for i in installations])

    return InstallationListResponse(
        items=[InstallationResponse.from_model(i, session_count=counts.get(i.id, 0)) for i in installations],
        total=len(installations),
    )


@router.get("/{installation_id}", response_model=InstallationDetailResponse)
@limiter.limit("30/minute")
async def get_installation(
    installation_id: int,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> InstallationDetailResponse:
    """Installation details with BYOK status and suppression labels."""
    installation = await _installation_or_404(session, installation_id)
    # Read-only: any member who sees it in the list can open it. Admin is
    # reserved for the credential and settings routes below.
    await verify_installation_access(user, installation, settings)
    await session.refresh(installation, ["byok_config"])

    return InstallationDetailResponse.from_model(installation)


@router.post("/{installation_id}/byok", response_model=BYOKConfigResponse)
@limiter.limit("10/minute")
async def post_byok(
    installation_id: int,
    body: BYOKConfigureRequest,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> BYOKConfigResponse:
    """Store a Claude credential for this installation."""
    installation = await _installation_or_404(session, installation_id)
    await verify_admin_permission(user, installation, settings)

    config = await configure_byok(session, installation.id, body.api_key, settings.FERNET_KEY.get_secret_value())
    return BYOKConfigResponse.model_validate(config)


@router.delete("/{installation_id}/byok", status_code=204)
@limiter.limit("10/minute")
async def delete_byok(
    installation_id: int,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> Response:
    """Remove the stored Claude credential."""
    installation = await _installation_or_404(session, installation_id)
    await verify_admin_permission(user, installation, settings)

    await delete_byok_config(session, installation.id)
    return Response(status_code=204)


@router.put("/{installation_id}/suppression-labels", response_model=SuppressionLabelsResponse)
@limiter.limit("10/minute")
async def put_suppression_labels(
    installation_id: int,
    body: SuppressionLabelsRequest,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> SuppressionLabelsResponse:
    """Set the PR labels that suppress session creation."""
    installation = await _installation_or_404(session, installation_id)
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
    user: CurrentUser,
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
) -> PaginatedSessionsResponse:
    """One page of session history for an installation, newest first."""
    installation = await _installation_or_404(session, installation_id)
    await verify_installation_access(user, installation, settings)

    page = max(page, 1)
    per_page = min(per_page, MAX_PAGE_SIZE)

    items, total = await sessions.list_for_installation(
        session,
        installation.id,
        page=page,
        per_page=per_page,
        status=ContainerStatus(status) if status else None,
    )

    return PaginatedSessionsResponse(
        items=[SessionSummaryResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if total else 0,
    )


@router.put("/{installation_id}/post-results", response_model=PostResultsSettingResponse)
@limiter.limit("10/minute")
async def put_post_results_setting(
    installation_id: int,
    body: PostResultsSettingRequest,
    request: Request,
    session: DbSession,
    settings: GetSettings,
    user: CurrentUser,
) -> PostResultsSettingResponse:
    """Enable or disable posting session results back to the PR."""
    installation = await _installation_or_404(session, installation_id)
    await verify_admin_permission(user, installation, settings)

    updated = await update_post_results_setting(session, installation.id, body.post_results_to_pr)
    return PostResultsSettingResponse(post_results_to_pr=updated.post_results_to_pr)
