"""Comprehension API request/response schemas.

Story 3.1 adds only the detail response schema — there are no request
schemas for a plain GET. Story 3.3 introduces streaming event schemas
alongside ``sse.py``.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from helprs.modules.comprehension.domain.value_objects import SessionRole, SessionStatus


class SessionResponse(BaseModel):
    """Serialized shape of ``GET /api/v1/sessions/{id}``.

    ``diff`` is fetched in memory from GitHub on every request and is
    NEVER persisted server-side (NFR13). ``question_count`` is
    hardcoded to ``0`` in Story 3.1 — Story 3.3 populates it once
    questions start landing in the DB.

    ``role`` and ``status`` are typed as ``StrEnum`` so Pydantic
    validates them at serialization time — a future typo in a new
    enum value fails fast instead of shipping silently.
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
    diff: str
    created_at: datetime
    updated_at: datetime
