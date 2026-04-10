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


class Topic(StrEnum):
    """Scoring dimensions questions can attach to.

    Seed set for Story 3.1. Epic 4's scoring story may append additional
    topics; because this is a ``StrEnum`` the DB / JSON representation is
    stable and additions are purely additive.
    """

    ARCHITECTURE = "architecture"
    EDGE_CASES = "edge_cases"
    TRADEOFFS = "tradeoffs"
    IMPACT = "impact"
    TESTING = "testing"
    CORRECTNESS = "correctness"
