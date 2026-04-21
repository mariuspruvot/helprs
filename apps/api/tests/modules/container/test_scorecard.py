"""Tests for scorecard extraction from Claude session output."""

from helprs.modules.container.scorecard import extract_scorecard


VALID_SCORECARD = """\
Some assistant text before the scorecard.

```helprs-scorecard
{
  "skill": "challenge-me",
  "version": 1,
  "questions_asked": 3,
  "questions_answered": 3,
  "dimensions": {
    "depth": 8,
    "clarity": 7,
    "rigor": 6
  },
  "summary": "Strong understanding of failure modes.",
  "highlights": ["Good instinct on idempotency"]
}
```

Some text after.
"""


def test_extract_valid_scorecard():
    result = extract_scorecard(VALID_SCORECARD)
    assert result is not None
    assert result["skill"] == "challenge-me"
    assert result["version"] == 1
    assert result["dimensions"] == {"depth": 8, "clarity": 7, "rigor": 6}
    assert result["summary"] == "Strong understanding of failure modes."
    assert result["highlights"] == ["Good instinct on idempotency"]


def test_extract_returns_none_when_no_block():
    assert extract_scorecard("Just some regular text without a scorecard") is None


def test_extract_returns_none_for_invalid_json():
    text = "```helprs-scorecard\n{invalid json}\n```"
    assert extract_scorecard(text) is None


def test_extract_returns_none_for_missing_required_fields():
    text = '```helprs-scorecard\n{"skill": "challenge-me"}\n```'
    assert extract_scorecard(text) is None


def test_extract_returns_none_for_wrong_dimension_count():
    text = """```helprs-scorecard
{
  "skill": "challenge-me",
  "version": 1,
  "dimensions": {"depth": 8, "clarity": 7},
  "summary": "Missing one dimension"
}
```"""
    assert extract_scorecard(text) is None


def test_extract_returns_none_for_out_of_range_scores():
    text = """```helprs-scorecard
{
  "skill": "challenge-me",
  "version": 1,
  "dimensions": {"depth": 11, "clarity": 7, "rigor": 6},
  "summary": "Score out of range"
}
```"""
    assert extract_scorecard(text) is None


def test_extract_returns_none_for_negative_scores():
    text = """```helprs-scorecard
{
  "skill": "challenge-me",
  "version": 1,
  "dimensions": {"depth": -1, "clarity": 7, "rigor": 6},
  "summary": "Negative score"
}
```"""
    assert extract_scorecard(text) is None


def test_extract_handles_float_scores():
    text = """```helprs-scorecard
{
  "skill": "eli5",
  "version": 1,
  "dimensions": {"accuracy": 7.5, "simplicity": 8.0, "completeness": 6.5},
  "summary": "Good explanation"
}
```"""
    result = extract_scorecard(text)
    assert result is not None
    assert result["dimensions"]["accuracy"] == 7.5


def test_extract_handles_different_skill_dimensions():
    text = """```helprs-scorecard
{
  "skill": "pair-debug",
  "version": 1,
  "dimensions": {"detection": 9, "methodology": 7, "speed": 8},
  "summary": "Found the bug quickly"
}
```"""
    result = extract_scorecard(text)
    assert result is not None
    assert result["skill"] == "pair-debug"
    assert set(result["dimensions"].keys()) == {"detection", "methodology", "speed"}
