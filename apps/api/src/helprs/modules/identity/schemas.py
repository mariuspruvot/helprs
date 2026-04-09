"""Identity API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    github_id: int
    github_login: str
    email: str | None
    avatar_url: str | None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    pass
