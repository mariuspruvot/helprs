"""Comprehension application command and query handlers.

Story 2.2 introduces ``StartSessionHandler`` — the use-case boundary
between the webhook adapter and the session-creation persistence path.

Story 3.1 adds ``GetSessionHandler`` — the use-case boundary for the
session detail read path. Kept colocated with ``StartSessionHandler``
so the CQRS seam is obvious (commands + queries live in the same
module, dispatched by the router / webhook adapter).

Neither handler performs HTTP itself. ``StartSessionHandler`` hands
off PR-comment posting to the webhook adapter; ``GetSessionHandler``
hands off the GitHub diff fetch to the router (which exits the DB
scope first — the pattern Epic 2's retrospective flagged as a blocker
for Story 3.3).
"""

from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.config import Settings
from helprs.core.exceptions import (
    DomainValidationError,
    ForbiddenError,
    NotFoundError,
)
from helprs.modules.comprehension.application.commands import StartSessionCommand
from helprs.modules.comprehension.application.queries import GetSessionQuery, GetSessionResult
from helprs.modules.comprehension.domain.entities import PRContext, Session
from helprs.modules.comprehension.domain.services import estimate_question_count
from helprs.modules.comprehension.infrastructure.repositories import SqlAlchemySessionRepository
from helprs.modules.installation.service import (
    get_default_suppression_labels,
    get_installation_by_github_id,
    get_installations_for_user,
    mint_installation_token,
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

        # TODO(story-3.5): replace with role-adaptive + large-PR sizing
        # (see FR39–FR41). Story 3.3 uses the minimal line-count
        # heuristic so the end-to-end flow ships first.
        total_questions = estimate_question_count(cmd.pr_diff_line_count) if cmd.pr_diff_line_count is not None else 5

        if len(existing) == 0:
            author, reviewer = await repo.add_pair(
                pr_ctx=pr_ctx,
                total_questions=total_questions,
            )
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
            author, reviewer = await repo.add_pair(
                pr_ctx=pr_ctx,
                total_questions=total_questions,
            )
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


class GetSessionHandler:
    """Load a session, verify repo access, and mint an installation token.

    The handler is intentionally **DB-only in spirit**: it does not
    fetch the PR diff. The router calls it, snapshots the result into
    locals, and then hits GitHub for the diff outside the handler.
    This sets the pattern precedent Epic 2's retrospective flagged as
    a blocker for Story 3.3 (where LLM calls will follow the same rule).

    Known acceptable exceptions — two outbound HTTP calls still run
    while holding the ``AsyncSession``:

    1. ``get_installations_for_user`` — calls GitHub ``/user/installations``
       to re-check FR26 access. Bounded by the 10 s httpx timeout.
    2. ``mint_installation_token`` — App-JWT → scoped token exchange
       (~100-300 ms, bounded by the same timeout).

    Both are accepted for Story 3.1 because inlining either would
    require either (a) duplicating the access-check query locally or
    (b) splitting the handler into a DB phase and an HTTP phase that
    the router orchestrates. The retro-driven full fix is owned by
    Story 3.3 prep, where LLM latency (>> diff fetch latency) makes
    the split mandatory.

    ``GetSessionQuery.requesting_user`` is the ``GitHubUser`` row
    already loaded by the ``get_current_user`` FastAPI dependency;
    the handler reuses it directly rather than re-issuing a ``SELECT``.

    .. warning::
       **SECURITY DEBT — installation-level access only.** The access
       check below validates installation membership, NOT repository
       membership. For GitHub Apps with
       ``repository_selection="selected"``, a user with access to ANY
       repo in an installation will be treated as having access to
       ALL sessions on that installation. This is a **BLOCKER for
       any `selected` install reaching production** and must be
       fixed before the MVP launch widens beyond
       ``repository_selection="all"``. The fix is an additional call
       to ``GET /user/installations/{id}/repositories`` and checking
       that ``domain_session.repo_full_name`` is in the response.
       Tracked in ``_bmad-output/implementation-artifacts/deferred-work.md``
       under "code review of story-3-2" (2026-04-10). Deferred so
       Story 3.3's read-path refactor can absorb the check instead
       of layering it twice.
    """

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def handle(self, query: GetSessionQuery) -> GetSessionResult:
        # 1. Load the session by id.
        repo = SqlAlchemySessionRepository(self._session)
        domain_session = await repo.get_by_id(session_id=query.session_id)
        if domain_session is None:
            raise NotFoundError(f"Session {query.session_id} not found")

        # 2. Verify the user has access to the session's installation.
        #    ``get_installations_for_user`` is the exact same function the
        #    ``/installations`` listing uses — identical FR26 semantics.
        #    The user is reused from the FastAPI dependency (no re-query).
        accessible = await get_installations_for_user(self._session, query.requesting_user, self._settings)
        if not any(i.id == domain_session.installation_id for i in accessible):
            raise ForbiddenError("You do not have access to this session's repository")

        # 3. Mint an installation token so the router can fetch the diff
        #    after the handler returns. Minting happens inside the DB
        #    scope intentionally — see class docstring "known acceptable
        #    exceptions".
        installation_token = await mint_installation_token(domain_session.github_installation_id, self._settings)

        # Story 3.3: count persisted questions for the detail response.
        question_count = await repo.count_questions(session_id=query.session_id)

        return GetSessionResult(
            session=domain_session,
            installation_token=installation_token,
            question_count=question_count,
        )
