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


class Verdict(StrEnum):
    """Session comprehension verdict derived from dimension score average."""

    EXCEPTIONAL = "exceptional"
    STRONG = "strong"
    ADEQUATE = "adequate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class ScoreDimension(StrEnum):
    """The four scoring axes evaluated by the scoring agent."""

    DEPTH = "depth"
    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    INSIGHT = "insight"


class ReportReason(StrEnum):
    """Reason a developer flags a question as problematic (UX-DR9)."""

    IRRELEVANT = "irrelevant"
    FACTUALLY_INCORRECT = "factually_incorrect"
    AMBIGUOUS = "ambiguous"
    TOO_EASY = "too_easy"
    TOO_HARD = "too_hard"
    OTHER = "other"


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
