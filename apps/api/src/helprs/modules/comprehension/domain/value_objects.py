"""Comprehension domain value objects."""

from enum import StrEnum


class SessionRole(StrEnum):
    """Which side of the PR a session challenges."""

    AUTHOR = "author"
    REVIEWER = "reviewer"


class SessionStatus(StrEnum):
    """Lifecycle state of a comprehension session."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
