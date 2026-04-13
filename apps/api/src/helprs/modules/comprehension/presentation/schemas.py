"""Comprehension API request/response schemas.

Story 3.1 adds only the detail response schema — there are no request
schemas for a plain GET. Story 3.3 introduces streaming event schemas
alongside ``sse.py``. Story 3.4 adds the answer-submission request +
the resume-progress sub-schemas.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from helprs.modules.comprehension.domain.value_objects import ReportReason, SessionRole, SessionStatus


class QuestionProgress(BaseModel):
    """Per-question progress entry returned in ``SessionResponse.progress``.

    Story 3.4: drives the frontend's resume-from-reload experience.
    The verbatim text is intentionally absent — FR35/NFR14 means we
    cannot show past content on resume. The frontend renders past
    cycles as compact "(text not retained)" placeholders.
    """

    number: int
    status: Literal["answered", "in_flight"]
    topic: str  # serialized ``Topic`` enum value


class ScoreResponse(BaseModel):
    """Story 4.1: score breakdown included in ``SessionResponse``.

    Nullable at the ``SessionResponse`` level — only present after
    the session is scored (status == COMPLETED).
    """

    depth: int
    accuracy: int
    completeness: int
    insight: int
    verdict: str
    gaps: list[str]


class SessionFeedbackResponse(BaseModel):
    """Story 4.2: serialized post-session feedback."""

    rating: bool
    comment: str | None
    created_at: datetime


class SessionResponse(BaseModel):
    """Serialized shape of ``GET /api/v1/sessions/{id}``.

    ``diff`` is fetched in memory from GitHub on every request and is
    NEVER persisted server-side (NFR13). Story 3.4 extends the shape
    with ``progress`` so the frontend knows how many cycles have
    already been answered when reopening the session.
    """

    id: UUID
    repo_full_name: str
    repo_owner: str
    repo_name: str
    pr_number: int
    pr_title: str
    role: SessionRole
    status: SessionStatus
    question_count: int
    # Story 3.3: total number of questions the session plans to ask
    # (set by ``estimate_question_count`` at session creation time).
    total_questions: int
    diff: str
    created_at: datetime
    updated_at: datetime
    # Story 3.4: per-question progress for resume support.
    progress: list[QuestionProgress]
    # Story 4.1: score breakdown — null before session is scored.
    score: ScoreResponse | None = None
    # Story 4.2: post-session feedback — null before feedback submitted.
    feedback: SessionFeedbackResponse | None = None


class SubmitAnswerRequest(BaseModel):
    """Body of ``POST /api/v1/sessions/{id}/answers``.

    Story 3.4: ``question_number`` is the 1-indexed position of the
    question being answered (resolved server-side to ``question_id``
    via ``get_question_by_number``). ``text`` is the verbatim answer
    body — bounded to 1..8000 chars to reject empty submissions and
    abusive payloads. The text is hashed (SHA-256) before persisting;
    the verbatim string never touches disk.

    The validator below rejects whitespace-only and zero-width-only
    payloads that slip past ``min_length=1`` (e.g. ``"   "``,
    ``"\\u200b"``). Trimmed length must be ≥ 1.
    """

    question_number: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=8000)

    @field_validator("text")
    @classmethod
    def _reject_blank(cls, v: str) -> str:
        # Strip ASCII whitespace + common zero-width / BOM code points.
        stripped = v.strip().strip("\u200b\u200c\u200d\ufeff")
        if not stripped:
            raise ValueError("text must not be blank or whitespace-only")
        return v


# ------------------------------------------------------------------
# Story 4.2: question report + session feedback schemas
# ------------------------------------------------------------------


class QuestionReportRequest(BaseModel):
    """Body of ``POST /api/v1/sessions/{id}/questions/{qnum}/report``."""

    reason: ReportReason


class QuestionReportResponse(BaseModel):
    """Confirmation of a question report."""

    session_id: UUID
    question_number: int
    reason: ReportReason
    created_at: datetime


class SessionFeedbackRequest(BaseModel):
    """Body of ``POST /api/v1/sessions/{id}/feedback``."""

    rating: bool
    comment: str | None = Field(None, max_length=2000)
