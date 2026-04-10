"""Comprehension domain interfaces (ports).

Story 2.2 introduces the ``SessionRepository`` port used by the
``StartSessionHandler`` to persist session pairs. Story 3.1 will add
``LLMProvider`` and expand the repository contract.
"""

from typing import Protocol
from uuid import UUID

from helprs.modules.comprehension.domain.entities import PRContext, Session


class SessionRepository(Protocol):
    """Port for persisting/loading session pairs.

    Implemented by ``SqlAlchemySessionRepository`` in the infrastructure
    layer. Exposes only the three operations Story 2.2 needs; additional
    methods (by-id lookup, status updates, …) land in Story 3.1.
    """

    async def add_pair(self, *, pr_ctx: PRContext) -> tuple[Session, Session]:
        """Insert an (author, reviewer) session pair for the PR.

        Returns the two domain entities with populated IDs. The underlying
        ORM session is flushed (to assign IDs) but NOT committed — the
        caller owns the unit of work.
        """
        ...

    async def update_head_sha(
        self,
        *,
        installation_id: UUID,
        repo_full_name: str,
        pr_number: int,
        new_head_sha: str,
        new_pr_title: str,
        new_pr_diff_url: str,
    ) -> list[Session]:
        """Update PR-head metadata on both rows of an existing pair.

        Returns the refreshed domain entities. Used on
        ``pull_request.synchronize`` to keep the session pointed at the
        latest commit without re-posting the PR comment.
        """
        ...

    async def find_pair(
        self,
        *,
        installation_id: UUID,
        repo_full_name: str,
        pr_number: int,
    ) -> list[Session]:
        """Look up the session pair for a given PR.

        Returns 0, 1 (corrupted — caller should recover), or 2 rows. The
        caller decides whether to create, recover, or update.
        """
        ...
