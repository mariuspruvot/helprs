"""Tests for rendering a session's scorecard as a PR comment.

The comment used to be regex-scraped out of the markdown a skill writes for
the live stream, with no validation, by a module that ran its own SQL over
the events table. It is rendered from the validated ``Scorecard`` now — the
same object the dashboard reads — so the two cannot disagree about a session.
"""

from uuid import uuid4

import pytest

from helprs.modules.container.pr_comment import build_session_url, format_pr_comment
from helprs.modules.container.scorecard import Scorecard


def _scorecard(**overrides) -> Scorecard:
    data = {
        "skill": "challenge-me",
        "version": 1,
        "questions_asked": 3,
        "questions_answered": 3,
        "dimensions": {"depth": 8, "clarity": 7, "rigor": 6},
        "summary": "Strong on failure modes, thinner on edge cases.",
        "highlights": ["Spotted the architectural trade-off"],
    }
    data.update(overrides)
    return Scorecard.model_validate(data)


class TestFormatPrComment:
    def test_shows_the_overall_score(self):
        body = format_pr_comment(_scorecard(), "https://helprs.tech/session/x")

        # (8 + 7 + 6) / 3
        assert "**Score: 7.0 / 10**" in body

    def test_lists_every_dimension(self):
        body = format_pr_comment(_scorecard(), "https://helprs.tech/session/x")

        for label, score in (("Depth", 8), ("Clarity", 7), ("Rigor", 6)):
            assert f"| {label} | {score} / 10 |" in body

    def test_includes_the_summary_and_highlights(self):
        body = format_pr_comment(_scorecard(), "https://helprs.tech/session/x")

        assert "Strong on failure modes" in body
        assert "- Spotted the architectural trade-off" in body

    def test_highlights_are_omitted_when_the_skill_sent_none(self):
        body = format_pr_comment(_scorecard(highlights=[]), "https://helprs.tech/session/x")

        assert "**Highlights**" not in body

    def test_includes_the_session_link_in_a_collapsed_block(self):
        url = "https://helprs.tech/session/abc/org/repo/42"
        body = format_pr_comment(_scorecard(), url)

        assert url in body
        assert "<details>" in body
        assert "</details>" in body

    def test_the_bar_tracks_the_score(self):
        top = format_pr_comment(_scorecard(dimensions={"a": 10, "b": 10, "c": 10}), "u")
        bottom = format_pr_comment(_scorecard(dimensions={"a": 0, "b": 0, "c": 0}), "u")

        assert "█" * 10 in top
        assert "░" * 10 in bottom


class TestScorecardValidation:
    """The gate that now decides whether a comment gets posted at all."""

    def test_a_score_outside_the_scale_is_rejected(self):
        with pytest.raises(ValueError, match="outside 0-10"):
            _scorecard(dimensions={"depth": 11, "clarity": 7, "rigor": 6})

    def test_the_wrong_number_of_dimensions_is_rejected(self):
        with pytest.raises(ValueError, match="exactly 3 dimensions"):
            _scorecard(dimensions={"depth": 8, "clarity": 7})

    def test_extra_fields_a_skill_reports_are_kept(self):
        """The declared fields are the contract, not the ceiling."""
        card = _scorecard(mood="cheerful")

        assert card.model_dump()["mood"] == "cheerful"

    def test_overall_score_is_the_mean(self):
        assert _scorecard(dimensions={"a": 3, "b": 4, "c": 5}).overall_score == 4


class TestBuildSessionUrl:
    def test_builds_correct_url(self):
        installation_id = uuid4()

        url = build_session_url("https://helprs.tech", installation_id, "org/repo", 42)

        assert url == f"https://helprs.tech/session/{installation_id}/org/repo/42"
