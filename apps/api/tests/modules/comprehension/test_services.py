"""Tests for comprehension.domain.services.

Story 3.5 locks the FR6 tier targets 4/6/8 into the
``estimate_question_count`` heuristic. These assertions cover all
tier boundaries (AC #13).
"""

import pytest

from helprs.modules.comprehension.domain.services import estimate_question_count


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
