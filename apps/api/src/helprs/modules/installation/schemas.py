"""Installation API schemas."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class BYOKConfigureRequest(BaseModel):
    api_key: str

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v or not v.startswith("sk-ant-"):
            raise ValueError("API key must start with 'sk-ant-'")
        if len(v) < 20:
            raise ValueError("API key is too short")
        return v


class BYOKConfigResponse(BaseModel):
    model_config = {"from_attributes": True}

    key_hint: str
    key_status: str
    validated_at: datetime | None


class SuppressionLabelsRequest(BaseModel):
    labels: list[str]

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v: list[str]) -> list[str]:
        # Strip whitespace and deduplicate while preserving order
        v = list(dict.fromkeys(label.strip() for label in v))
        if len(v) > 20:
            raise ValueError("Maximum 20 suppression labels allowed")
        for label in v:
            if len(label) > 50:
                raise ValueError(f"Label '{label}' exceeds maximum 50 characters")
            if not re.match(r"^[a-zA-Z0-9\-]+$", label):
                raise ValueError(f"Label '{label}' contains invalid characters. Only alphanumeric and hyphens allowed")
        return v


class SuppressionLabelsResponse(BaseModel):
    labels: list[str]


class InstallationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    github_installation_id: int
    account_login: str
    account_type: str
    repository_selection: str
    suspended_at: datetime | None
    created_at: datetime
    byok_configured: bool = False
    byok_key_hint: str | None = None
    byok_key_status: str | None = None
    byok_validated_at: datetime | None = None
    suppression_labels: list[str] = []
    session_count: int = 0


class InstallationDetailResponse(InstallationResponse):
    pass


class InstallationListResponse(BaseModel):
    items: list[InstallationResponse]
    total: int


class SessionSummaryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    pr_number: int
    repo_full_name: str
    skill_name: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class PaginatedSessionsResponse(BaseModel):
    items: list[SessionSummaryResponse]
    total: int
    page: int
    per_page: int
    total_pages: int
