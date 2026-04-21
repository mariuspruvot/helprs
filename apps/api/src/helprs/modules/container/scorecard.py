"""Scorecard extraction from Claude session output.

Skills emit a structured JSON scorecard wrapped in a fenced code block
tagged `helprs-scorecard`. This module parses it from the last assistant
message text.
"""

import json
import re

SCORECARD_PATTERN = re.compile(
    r"```helprs-scorecard\s*\n(.*?)\n```",
    re.DOTALL,
)

REQUIRED_FIELDS = {"skill", "version", "dimensions", "summary"}


def extract_scorecard(text: str) -> dict | None:
    """Extract the helprs-scorecard JSON block from text.

    Returns the parsed dict if found and valid, None otherwise.
    """
    match = SCORECARD_PATTERN.search(text)
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    if not REQUIRED_FIELDS.issubset(data.keys()):
        return None

    dims = data.get("dimensions")
    if not isinstance(dims, dict) or len(dims) != 3:
        return None

    for value in dims.values():
        if not isinstance(value, (int, float)) or value < 0 or value > 10:
            return None

    return data
