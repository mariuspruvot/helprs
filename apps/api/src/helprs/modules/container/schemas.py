"""Container session API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class CreateSessionRequest(BaseModel):
    """Request body for creating a new container session."""

    installation_id: int
    pr_number: int
    repo_full_name: str
    skill_name: str

    @field_validator("repo_full_name")
    @classmethod
    def validate_repo_full_name(cls, v: str) -> str:
        if "/" not in v or v.count("/") != 1:
            raise ValueError("repo_full_name must be in 'owner/repo' format")
        owner, repo = v.split("/")
        if not owner or not repo:
            raise ValueError("repo_full_name must be in 'owner/repo' format")
        return v

    @field_validator("pr_number")
    @classmethod
    def validate_pr_number(cls, v: int) -> int:
        if v < 1:
            raise ValueError("pr_number must be a positive integer")
        return v

    @field_validator("skill_name")
    @classmethod
    def validate_skill_name(cls, v: str) -> str:
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("skill_name must be alphanumeric with hyphens/underscores")
        return v


class ContainerSessionResponse(BaseModel):
    """Response schema for a container session."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    installation_id: uuid.UUID
    user_id: uuid.UUID | None
    pr_number: int
    repo_full_name: str
    skill_name: str
    container_id: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    scorecard: dict | None = None
    xp_earned: int | None = None
    created_at: datetime
    updated_at: datetime


class SendMessageRequest(BaseModel):
    """Request body for sending a message to a running container session."""

    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v


class SendMessageResponse(BaseModel):
    """Response after sending a message to a container session."""

    session_id: uuid.UUID
    status: str
    message: str


class StopSessionResponse(BaseModel):
    """Response when stopping a container session."""

    id: uuid.UUID
    status: str
    message: str


class SessionEventResponse(BaseModel):
    """A single persisted stream-json event."""

    model_config = {"from_attributes": True}

    event_id: int
    data: dict
    created_at: datetime


class SessionEventsListResponse(BaseModel):
    """All persisted events for a session."""

    session_id: uuid.UUID
    events: list[SessionEventResponse]
    total: int


class ScorecardResponse(BaseModel):
    """Parsed scorecard for a completed session."""

    session_id: uuid.UUID
    scorecard: dict | None
    xp_earned: int | None
