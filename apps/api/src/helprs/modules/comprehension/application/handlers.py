"""Comprehension application command and query handlers.

Story 2.2 introduces ``StartSessionHandler`` — the use-case boundary
between the webhook adapter and the session-creation persistence path.
It owns:

* installation lookup
* suppression-label evaluation (with default-labels fallback)
* session-pair creation (opened) or in-place update (synchronize)
* orphan recovery for the edge case of a single stray row

It does **not** perform HTTP (token minting + PR-comment posting live in
the webhook adapter / installation service). Story 3.1 may refactor
this to a ``PRCommentPublisher`` port once a second publisher exists.
"""

from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.exceptions import DomainValidationError, NotFoundError
from helprs.modules.comprehension.application.commands import StartSessionCommand
from helprs.modules.comprehension.domain.entities import PRContext, Session
from helprs.modules.comprehension.infrastructure.repositories import SqlAlchemySessionRepository
from helprs.modules.installation.service import (
    get_default_suppression_labels,
    get_installation_by_github_id,
)

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class StartSessionResult:
    """Outcome of a ``StartSessionHandler.handle`` call.

    ``created`` — True iff rows were newly inserted (0→2 path or orphan
    recovery). False on synchronize-with-existing-pair and suppression.

    ``comment_needed`` — True iff the webhook adapter should post the PR
    comment. Distinct from ``created`` because we want the adapter to
    post on the 0→2 path whether triggered by ``opened`` or
    ``synchronize`` (race-condition guard, AC #5).
    """

    created: bool
    suppressed: bool
    suppressed_by_label: str | None
    sessions: tuple[Session, Session] | None
    comment_needed: bool


class StartSessionHandler:
    """Application handler: create (or update) a session pair for a PR.

    Pure business logic — does not mint GitHub tokens or post comments.
    The webhook adapter composes this with ``post_pr_comment_with_retry``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def handle(self, cmd: StartSessionCommand) -> StartSessionResult:
        installation = await get_installation_by_github_id(
            self._session,
            cmd.github_installation_id,
        )
        if installation is None:
            # Webhook arrived for an installation we don't know about (or
            # it was soft-deleted). This is a real bug state — the webhook
            # event row should transition to ``failed`` so operators see
            # it, so we raise rather than log-and-continue.
            raise NotFoundError(f"Installation not found for github_installation_id={cmd.github_installation_id}")

        # ---- Suppression label evaluation ---------------------------------
        # ``suppression_labels`` is ``list | None``; both ``None`` and ``[]``
        # fall back to the defaults (addresses Epic-1 deferred #1).
        effective_labels = installation.suppression_labels or get_default_suppression_labels()
        pr_label_lookup = {label.lower() for label in cmd.pr_labels}
        matched_label = next(
            (label for label in effective_labels if label.lower() in pr_label_lookup),
            None,
        )
        if matched_label is not None:
            await logger.ainfo(
                "session_suppressed_by_label",
                label=matched_label,
                repo_full_name=cmd.repo_full_name,
                pr_number=cmd.pr_number,
            )
            return StartSessionResult(
                created=False,
                suppressed=True,
                suppressed_by_label=matched_label,
                sessions=None,
                comment_needed=False,
            )

        # ---- Session lookup / creation / update ---------------------------
        repo = SqlAlchemySessionRepository(self._session)
        existing = await repo.find_pair(
            installation_id=installation.id,
            repo_full_name=cmd.repo_full_name,
            pr_number=cmd.pr_number,
        )

        pr_ctx = PRContext(
            installation_id=installation.id,
            github_installation_id=cmd.github_installation_id,
            repo_full_name=cmd.repo_full_name,
            repo_owner=cmd.repo_owner,
            repo_name=cmd.repo_name,
            pr_number=cmd.pr_number,
            pr_title=cmd.pr_title,
            pr_head_sha=cmd.pr_head_sha,
            pr_diff_url=cmd.pr_diff_url,
        )

        if len(existing) == 0:
            author, reviewer = await repo.add_pair(pr_ctx=pr_ctx)
            pair: tuple[Session, Session] = (author, reviewer)
            created = True
            comment_needed = True
        elif len(existing) == 2:
            refreshed = await repo.update_head_sha(
                installation_id=installation.id,
                repo_full_name=cmd.repo_full_name,
                pr_number=cmd.pr_number,
                new_head_sha=cmd.pr_head_sha,
                new_pr_title=cmd.pr_title,
                new_pr_diff_url=cmd.pr_diff_url,
            )
            # ``find_pair`` orders by ``role`` — AUTHOR < REVIEWER alphabetically.
            pair = (refreshed[0], refreshed[1])
            created = False
            comment_needed = False
        elif len(existing) == 1:
            # Rare: 1 row. DB corruption or a partial historical migration.
            # Wipe the stray row and re-create the pair.
            orphan = existing[0]
            await logger.awarning(
                "session_pair_corrupted",
                repo_full_name=cmd.repo_full_name,
                pr_number=cmd.pr_number,
                orphan_role=orphan.role.value,
                orphan_session_id=str(orphan.id),
            )
            await repo.delete_one(session_id=orphan.id)
            author, reviewer = await repo.add_pair(pr_ctx=pr_ctx)
            pair = (author, reviewer)
            created = True
            comment_needed = True
        else:
            # ``sessions`` has a unique (installation_id, repo_full_name,
            # pr_number, role) constraint, so at most 2 rows can exist for
            # a single PR. Reaching this branch (>2) means the DB state is
            # corrupted beyond what orphan recovery can safely fix — the
            # constraint itself would have already rejected the third row.
            # Refuse to touch the data and let the operator intervene.
            raise DomainValidationError(
                f"session pair lookup returned {len(existing)} rows "
                f"for (installation_id={installation.id}, "
                f"repo_full_name={cmd.repo_full_name!r}, pr_number={cmd.pr_number}); "
                "expected 0, 1, or 2"
            )

        # Bind the author-session id as the correlation ID for the rest of
        # this task. Using the author side as the canonical ID keeps logs
        # joinable even though two rows were written.
        structlog.contextvars.bind_contextvars(session_id=str(pair[0].id))

        return StartSessionResult(
            created=created,
            suppressed=False,
            suppressed_by_label=None,
            sessions=pair,
            comment_needed=comment_needed,
        )
