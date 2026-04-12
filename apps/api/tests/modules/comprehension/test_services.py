"""Tests for comprehension.domain.services.

Story 3.5 locks the FR6 tier targets 4/6/8 into the
``estimate_question_count`` heuristic. These assertions cover all
tier boundaries (AC #13).

Story 4.1 adds ``TestDeriveVerdict`` — deterministic verdict mapping
from four dimension scores. ``TestScoreEntity`` validates the frozen
dataclass shape and the ``Verdict``/``ScoreDimension`` enums.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from helprs.modules.comprehension.domain.entities import Score
from helprs.modules.comprehension.domain.services import derive_verdict, estimate_question_count
from helprs.modules.comprehension.domain.value_objects import ScoreDimension, Verdict


class TestEstimateQuestionCount:
    @pytest.mark.parametrize("diff_lines", [0, 1, 50, 99])
    def test_small_tier_returns_4(self, diff_lines: int) -> None:
        assert estimate_question_count(diff_lines) == 4

    @pytest.mark.parametrize("diff_lines", [100, 300, 499])
    def test_medium_tier_returns_6(self, diff_lines: int) -> None:
        assert estimate_question_count(diff_lines) == 6

    @pytest.mark.parametrize("diff_lines", [500, 1500, 2000, 10_000])
    def test_large_tier_returns_8(self, diff_lines: int) -> None:
        assert estimate_question_count(diff_lines) == 8

    def test_negative_diff_lines_falls_into_smallest_tier(self) -> None:
        assert estimate_question_count(-1) == 4
        assert estimate_question_count(-10_000) == 4


class TestVerdictEnum:
    def test_all_values(self) -> None:
        assert Verdict.EXCEPTIONAL == "exceptional"
        assert Verdict.STRONG == "strong"
        assert Verdict.ADEQUATE == "adequate"
        assert Verdict.WEAK == "weak"
        assert Verdict.INSUFFICIENT == "insufficient"

    def test_count(self) -> None:
        assert len(Verdict) == 5


class TestScoreDimensionEnum:
    def test_all_values(self) -> None:
        assert ScoreDimension.DEPTH == "depth"
        assert ScoreDimension.ACCURACY == "accuracy"
        assert ScoreDimension.COMPLETENESS == "completeness"
        assert ScoreDimension.INSIGHT == "insight"

    def test_count(self) -> None:
        assert len(ScoreDimension) == 4


class TestDeriveVerdict:
    @pytest.mark.parametrize(
        "scores,expected",
        [
            ((10, 10, 10, 10), Verdict.EXCEPTIONAL),
            ((9, 9, 9, 9), Verdict.EXCEPTIONAL),
            ((9, 10, 8, 10), Verdict.EXCEPTIONAL),  # avg 9.25 → 9
            ((8, 8, 8, 8), Verdict.STRONG),
            ((7, 7, 7, 7), Verdict.STRONG),
            ((7, 7, 7, 8), Verdict.STRONG),  # avg 7.25 → 7
            ((6, 6, 6, 6), Verdict.ADEQUATE),
            ((5, 5, 5, 5), Verdict.ADEQUATE),
            ((4, 4, 4, 4), Verdict.WEAK),
            ((3, 3, 3, 3), Verdict.WEAK),
            ((2, 2, 2, 2), Verdict.INSUFFICIENT),
            ((0, 0, 0, 0), Verdict.INSUFFICIENT),
            ((1, 1, 1, 1), Verdict.INSUFFICIENT),
        ],
    )
    def test_verdict_thresholds(self, scores: tuple[int, ...], expected: Verdict) -> None:
        assert derive_verdict(*scores) == expected

    def test_rounding_boundary(self) -> None:
        # avg = (8+8+9+9)/4 = 8.5 → rounds to 8 → Strong (not Exceptional)
        assert derive_verdict(8, 8, 9, 9) == Verdict.STRONG
        # avg = (8+9+9+9)/4 = 8.75 → rounds to 9 → Exceptional
        assert derive_verdict(8, 9, 9, 9) == Verdict.EXCEPTIONAL


class TestScoreEntity:
    def test_frozen(self) -> None:
        score = Score(
            session_id=uuid4(),
            depth=7,
            accuracy=8,
            completeness=6,
            insight=7,
            verdict=Verdict.STRONG,
            gap_summary=("area 1", "area 2"),
            created_at=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            score.depth = 5  # type: ignore[misc]

    def test_fields(self) -> None:
        sid = uuid4()
        now = datetime.now(UTC)
        score = Score(
            session_id=sid,
            depth=7,
            accuracy=8,
            completeness=6,
            insight=7,
            verdict=Verdict.STRONG,
            gap_summary=("test gap",),
            created_at=now,
        )
        assert score.session_id == sid
        assert score.depth == 7
        assert score.accuracy == 8
        assert score.completeness == 6
        assert score.insight == 7
        assert score.verdict == Verdict.STRONG
        assert score.gap_summary == ("test gap",)
        assert score.created_at == now
