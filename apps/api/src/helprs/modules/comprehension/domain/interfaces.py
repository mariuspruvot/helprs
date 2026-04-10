"""Comprehension domain interfaces (ports).

Story 2.2 introduced the ``SessionRepository`` port used by the
``StartSessionHandler`` to persist session pairs. Story 3.1 extends the
repository contract with ``get_by_id`` (for the GET endpoint) and adds
the ``LLMProvider`` port — the contract Story 3.3's PydanticAI provider
will implement.
"""

from typing import Protocol
from uuid import UUID

from helprs.modules.comprehension.domain.entities import PRContext, Session
from helprs.modules.comprehension.domain.value_objects import SessionRole


class SessionRepository(Protocol):
    """Port for persisting/loading session pairs.

    Implemented by ``SqlAlchemySessionRepository`` in the infrastructure
    layer. Story 2.2's three methods stay untouched; Story 3.1 adds
    ``get_by_id`` for the detail endpoint.
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

    async def get_by_id(self, *, session_id: UUID) -> Session | None:
        """Load a single session by primary key.

        Returns ``None`` when the row is absent. Used by the detail
        endpoint and the forthcoming question/answer submission paths.
        """
        ...


class LLMProvider(Protocol):
    """Port for LLM calls.

    Story 3.1 only declares the contract so application-layer code can
    depend on a stable shape; the concrete ``PydanticAILLMProvider``
    ships in Story 3.3. The call sites pass the in-memory PR diff and
    the user's decrypted BYOK key as plain strings — neither is
    persisted anywhere along this path (FR35/NFR13).
    """

    async def generate_question(
        self,
        *,
        pr_diff: str,
        role: SessionRole,
        previous_questions: list[str],
        api_key: str,
    ) -> str: ...

    async def generate_feedback(
        self,
        *,
        question: str,
        answer: str,
        pr_diff: str,
        api_key: str,
    ) -> str: ...
