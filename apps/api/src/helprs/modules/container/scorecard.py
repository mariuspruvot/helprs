"""The structured scorecard a skill emits at the end of a session.

Skills write two things when they finish: markdown results for the human
watching the stream, and this JSON block for anything that has to *read* the
outcome. Both are documented in ``skills/challenge-me/CLAUDE.md``.

Everything machine-consumed goes through the model below, so the dashboard
and the PR comment can never disagree about a session. The PR comment used to
be regex-scraped out of the markdown instead, with no validation, so a small
wording drift in a skill silently produced no comment at all.
"""

import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SCORECARD_PATTERN = re.compile(
    r"```helprs-scorecard\s*\n(.*?)\n```",
    re.DOTALL,
)

DIMENSION_COUNT = 3
MAX_DIMENSION_SCORE = 10


class Scorecard(BaseModel):
    """A skill's verdict on one session.

    ``extra="allow"`` because a skill may report more than helPRs reads: the
    fields below are the contract, not the ceiling.
    """

    model_config = ConfigDict(extra="allow")

    skill: str
    version: int
    dimensions: dict[str, float]
    summary: str
    questions_asked: int | None = None
    questions_answered: int | None = None
    highlights: list[str] = Field(default_factory=list)

    @field_validator("dimensions")
    @classmethod
    def check_dimensions(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) != DIMENSION_COUNT:
            raise ValueError(f"expected exactly {DIMENSION_COUNT} dimensions, got {len(value)}")
        for name, score in value.items():
            if not 0 <= score <= MAX_DIMENSION_SCORE:
                raise ValueError(f"dimension '{name}' is {score}, outside 0-{MAX_DIMENSION_SCORE}")
        return value

    @property
    def overall_score(self) -> float:
        """Mean of the dimensions, on the same 0-10 scale."""
        return sum(self.dimensions.values()) / len(self.dimensions)


def extract_scorecard(text: str) -> Scorecard | None:
    """Parse the ``helprs-scorecard`` block out of text.

    Returns ``None`` rather than raising: a session whose skill emitted no
    scorecard, or emitted a malformed one, is a session without a scorecard --
    not a failed session.
    """
    match = SCORECARD_PATTERN.search(text)
    if not match:
        return None

    try:
        return Scorecard.model_validate(json.loads(match.group(1)))
    except (json.JSONDecodeError, ValueError, ValidationError):
        return None
