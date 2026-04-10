"""Comprehension domain entities.

Story 2.2 introduces the minimal ``Session`` + ``PRContext`` needed for
session-pair creation and PR-comment posting. Story 3.1 will promote
``Session`` to a full aggregate and add ``Question``/``Answer`` siblings.

Dependency rule: domain imports nothing outside stdlib + Pydantic. No
SQLAlchemy here — ORM mapping lives in ``infrastructure/repositories.py``.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from helprs.modules.comprehension.domain.value_objects import SessionRole, SessionStatus


@dataclass(frozen=True, slots=True)
class PRContext:
    """Value object carrying the PR metadata needed to create a session pair.

    Passed from the webhook handler down through the application layer into
    the repository. Frozen + slotted keeps it cheap and prevents mutation.
    """

    installation_id: UUID
    github_installation_id: int
    repo_full_name: str
    repo_owner: str
    repo_name: str
    pr_number: int
    pr_title: str
    pr_head_sha: str
    pr_diff_url: str

    def to_columns(self) -> dict:
        """Explode into the shared subset of columns every session row needs.

        Returned as a fresh dict (not cached) so callers can mutate it with
        ``role``/``status`` overrides without touching the value object.
        """
        return {
            "installation_id": self.installation_id,
            "github_installation_id": self.github_installation_id,
            "repo_full_name": self.repo_full_name,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "pr_number": self.pr_number,
            "pr_title": self.pr_title,
            "pr_head_sha": self.pr_head_sha,
            "pr_diff_url": self.pr_diff_url,
        }


@dataclass(slots=True)
class Session:
    """Domain representation of a comprehension session.

    Mutable (not frozen) because ``pr_head_sha``/``pr_title``/``pr_diff_url``
    are updated on ``pull_request.synchronize``. Story 3.1 will expand this
    into a proper aggregate with Questions/Answers.
    """

    id: UUID
    installation_id: UUID
    github_installation_id: int
    repo_full_name: str
    repo_owner: str
    repo_name: str
    pr_number: int
    pr_title: str
    pr_head_sha: str
    pr_diff_url: str
    role: SessionRole
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
