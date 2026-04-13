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

from helprs.modules.comprehension.domain.value_objects import ReportReason, SessionRole, SessionStatus, Topic, Verdict


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
    are updated on ``pull_request.synchronize``. Story 3.1 expands the
    aggregate family with ``Question``/``Answer`` siblings, but the
    ``Session`` shape itself is left untouched — the ``_to_domain`` mapping
    in ``infrastructure/repositories.py`` depends on the exact field set.
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
    # Story 3.3: number of questions this session plans to ask, set at
    # creation time by ``estimate_question_count``. Zero on legacy rows
    # created before the Story 3.3 migration — the SSE endpoint falls
    # back to ``5`` in that case.
    total_questions: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Question:
    """A Socratic question posed during a comprehension session.

    Only a SHA-256 hash of the verbatim text is stored (``text_hash``).
    The raw question is regenerated on demand by the LLM port and is
    never persisted — this enforces FR35/NFR14 at the type level: there
    is no ``text: str`` field for infrastructure to write.
    """

    id: UUID
    session_id: UUID
    number: int  # 1-indexed position in the session (1..N)
    topic: Topic
    text_hash: str  # SHA-256 of the verbatim text
    created_at: datetime


@dataclass(slots=True)
class Answer:
    """A developer's answer to a ``Question``.

    As with ``Question``, only ``text_hash`` is ever persisted. Latency
    is tracked for observability / scoring in Epic 4.
    """

    id: UUID
    question_id: UUID
    text_hash: str  # SHA-256 of the verbatim text
    latency_ms: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Score:
    """Comprehension score computed once per session.

    Frozen — scores are immutable after computation. The LLM produces
    the four dimension scores (0-10); the verdict is derived
    deterministically from the average in ``derive_verdict``.
    ``gap_summary`` is 2-4 growth-oriented bullet points.
    """

    session_id: UUID
    depth: int  # 0-10
    accuracy: int  # 0-10
    completeness: int  # 0-10
    insight: int  # 0-10
    verdict: Verdict
    gap_summary: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class QuestionReport:
    """A developer's flag on a problematic question.

    Frozen — reports are immutable after submission. References the
    question by ``session_id + question_number`` (metadata-only, no
    verbatim text stored — FR35/NFR14).
    """

    session_id: UUID
    question_number: int
    reason: ReportReason
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SessionFeedback:
    """Post-session thumbs up/down + optional comment.

    Frozen — feedback is immutable after submission. ``rating`` is
    True for thumbs-up, False for thumbs-down. ``comment`` is
    user-authored text, not AI content.
    """

    session_id: UUID
    rating: bool
    comment: str | None
    created_at: datetime
