"""Typed shapes at the webhook boundary.

GitHub's payloads arrive as raw JSON. Parsing them here, once, is what keeps
raw dictionaries out of the use cases: ``installation.service`` used to index
``webhook_data["installation"]["account"]["login"]`` itself, which turned a
GitHub shape change into a KeyError deep inside a use case instead of a
validation error at the edge.

Only the fields helPRs actually reads are modelled; ``extra="ignore"`` lets
the rest of GitHub's payload through untouched.
"""

from pydantic import BaseModel, ConfigDict, Field


class WebhookDelivery(BaseModel):
    """The transport-level facts about one delivery, from headers and body."""

    model_config = ConfigDict(extra="ignore")

    delivery_id: str = Field(min_length=1)
    event_type: str
    action: str | None
    github_installation_id: int | None
    payload: dict[str, object]


class WebhookAck(BaseModel):
    """What the receiver returns once the delivery is safely persisted."""

    status: str = "ok"
    duplicate: bool
