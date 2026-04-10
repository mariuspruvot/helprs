"""Webhook event handlers."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import get_settings
from helprs.modules.comprehension.application.commands import StartSessionCommand
from helprs.modules.comprehension.application.handlers import StartSessionHandler
from helprs.modules.installation.service import (
    create_installation,
    mint_installation_token,
    post_pr_comment_with_retry,
    soft_delete_installation,
    suspend_installation,
    unsuspend_installation,
)

logger = structlog.get_logger()


def _extract_installation_id(payload: dict) -> int:
    """Extract installation ID from webhook payload, raising ValueError on missing fields."""
    try:
        return payload["installation"]["id"]
    except (KeyError, TypeError) as e:
        raise ValueError(f"Malformed webhook payload: missing installation.id ({e})") from e


async def handle_installation_created(payload: dict, session: AsyncSession) -> None:
    """Handle installation.created webhook event."""
    installation = await create_installation(session, payload)
    await logger.ainfo(
        "webhook_installation_created",
        installation_id=str(installation.id),
        github_installation_id=installation.github_installation_id,
    )


async def handle_installation_deleted(payload: dict, session: AsyncSession) -> None:
    """Handle installation.deleted webhook event."""
    github_id = _extract_installation_id(payload)
    result = await soft_delete_installation(session, github_id)
    if result:
        await logger.ainfo(
            "webhook_installation_deleted",
            github_installation_id=github_id,
        )
    else:
        await logger.awarning(
            "webhook_installation_delete_not_found",
            github_installation_id=github_id,
        )


async def handle_installation_suspended(payload: dict, session: AsyncSession) -> None:
    """Handle installation.suspended webhook event."""
    github_id = _extract_installation_id(payload)
    result = await suspend_installation(session, github_id)
    if result:
        await logger.ainfo(
            "webhook_installation_suspended",
            github_installation_id=github_id,
        )
    else:
        await logger.awarning(
            "webhook_installation_suspend_not_found",
            github_installation_id=github_id,
        )


async def handle_installation_unsuspended(payload: dict, session: AsyncSession) -> None:
    """Handle installation.unsuspended webhook event."""
    github_id = _extract_installation_id(payload)
    result = await unsuspend_installation(session, github_id)
    if result:
        await logger.ainfo(
            "webhook_installation_unsuspended",
            github_installation_id=github_id,
        )
    else:
        await logger.awarning(
            "webhook_installation_unsuspend_not_found",
            github_installation_id=github_id,
        )


def _build_comment_body(app_base_url: str, author_id: str, reviewer_id: str) -> str:
    """Compose the PR comment body with per-role session links.

    Warm tone, ~3 lines of content. GitHub's per-comment limit is 65536
    bytes so truncation is not a concern; brevity is driven by UX — PR
    comments are noisy and this one should respect that.
    """
    base = app_base_url.rstrip("/")
    return (
        "helPRs is ready to walk through this PR with you.\n\n"
        f"→ Author challenge: {base}/sessions/{author_id}\n"
        f"→ Reviewer challenge: {base}/sessions/{reviewer_id}\n\n"
        "Questions are AI-generated. Each session takes ~10 min."
    )


async def _handle_pull_request_common(
    payload: dict,
    session: AsyncSession,
    action: str,
) -> None:
    """Shared pull_request handler for opened / synchronize.

    The opened-vs-synchronize distinction is carried by the handler
    result, not branched here — per AC #5 the synchronize path MUST
    create sessions (and post the comment) when none exist yet, which
    means the logic is identical at this level.
    """
    # Defensive payload parsing — any KeyError/TypeError should log and
    # return without raising. A malformed payload is a GitHub bug or a
    # GitHub schema change, not something we should mark ``failed``.
    try:
        github_installation_id = payload["installation"]["id"]
        pr = payload["pull_request"]
        repo = payload["repository"]
        pr_number = pr["number"]
        pr_title = pr["title"]
        pr_head_sha = pr["head"]["sha"]
        pr_diff_url = pr["diff_url"]
        repo_full_name = repo["full_name"]
        repo_owner = repo["owner"]["login"]
        repo_name = repo["name"]
        # Keep only labels with a usable string name. GitHub's schema
        # guarantees this today, but a replayed / manually-edited payload
        # could carry ``null`` or non-string values — drop them silently
        # rather than crash the downstream ``.lower()`` suppression check.
        pr_labels = tuple(
            lbl["name"]
            for lbl in (pr.get("labels") or [])
            if isinstance(lbl, dict) and isinstance(lbl.get("name"), str)
        )
    except (KeyError, TypeError) as exc:
        await logger.awarning(
            "pull_request_event_malformed_payload",
            action=action,
            error=str(exc),
        )
        return

    # Bind PR-scope context on top of the task-scope bindings from
    # process_webhook_event (delivery_id / event_type / action /
    # github_installation_id). ``session_id`` is bound later by the
    # application handler once the row exists.
    structlog.contextvars.bind_contextvars(
        repo_full_name=repo_full_name,
        pr_number=pr_number,
    )

    cmd = StartSessionCommand(
        github_installation_id=github_installation_id,
        repo_full_name=repo_full_name,
        repo_owner=repo_owner,
        repo_name=repo_name,
        pr_number=pr_number,
        pr_title=pr_title,
        pr_head_sha=pr_head_sha,
        pr_diff_url=pr_diff_url,
        pr_labels=pr_labels,
        # TODO(story-3.5): fetch the PR diff here to compute
        # ``pr_diff_line_count`` so ``estimate_question_count`` gets a
        # non-``None`` input. Currently ``None`` → the handler falls
        # back to ``total_questions=5`` for every PR, which is fine for
        # Story 3.3's minimal heuristic but defeats the point of the
        # size-tiered sizing. Story 3.5 rewrites the heuristic anyway,
        # so the diff-fetch wiring is tracked as part of that story.
        pr_diff_line_count=None,
    )

    handler = StartSessionHandler(session)
    result = await handler.handle(cmd)

    if result.suppressed:
        # Handler already emitted ``session_suppressed_by_label``.
        return

    if not result.comment_needed:
        # Synchronize path with an existing pair — rows were updated in
        # place, no PR comment to post.
        await logger.ainfo("session_pair_updated", action=action)
        return

    if result.sessions is None:
        # StartSessionResult invariant: comment_needed=True implies sessions
        # are populated. Defensive check in case the invariant is ever
        # broken by a future refactor — ``assert`` alone is stripped under
        # ``python -O``.
        raise RuntimeError("StartSessionResult returned comment_needed=True with sessions=None")
    author, reviewer = result.sessions

    settings = get_settings()
    installation_token = await mint_installation_token(github_installation_id, settings)
    body = _build_comment_body(settings.APP_BASE_URL, str(author.id), str(reviewer.id))
    await post_pr_comment_with_retry(
        owner=repo_owner,
        repo=repo_name,
        pr_number=pr_number,
        body=body,
        installation_token=installation_token,
    )
    await logger.ainfo("pr_comment_posted", action=action)


async def handle_pull_request_opened(payload: dict, session: AsyncSession) -> None:
    """Handle pull_request.opened webhook event."""
    await _handle_pull_request_common(payload, session, "opened")


async def handle_pull_request_synchronize(payload: dict, session: AsyncSession) -> None:
    """Handle pull_request.synchronize webhook event."""
    await _handle_pull_request_common(payload, session, "synchronize")
