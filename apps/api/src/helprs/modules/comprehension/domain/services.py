"""Comprehension domain services.

Pure, stdlib-only domain helpers. No SQLAlchemy imports, no HTTP,
no side effects — this module must stay dependency-free so the
domain-purity test keeps passing.

Story 3.5 replaces the Story 3.3 3/5/7 heuristic with the FR6 tier
targets 4/6/8 (mid-of-range picks for the three size buckets). The
single-int return preserves the ``Session.total_questions: int``
schema (no migration).

Story 4.1 adds ``derive_verdict`` — deterministic mapping from the
average of the four dimension scores to a ``Verdict`` enum value.
The LLM produces the raw scores; Python produces the verdict.
"""

from helprs.modules.comprehension.domain.value_objects import Verdict


def estimate_question_count(diff_lines: int) -> int:
    """Size a session per FR6 tiers.

    * ``< 100`` lines  → 4 questions  (small; range 3-5, pick mid)
    * ``100–499``      → 6 questions  (medium; range 5-7, pick mid)
    * ``>= 500``       → 8 questions  (large; range 7-10, pick lower-mid)

    Negative or zero line counts fall into the smallest tier — no
    need to raise, the SSE stream handles 0-question sessions as a
    zero-iteration loop. A huge (>= 2000 lines) PR is still "large"
    for sizing purposes — the large-PR handling rule (FR11, Story 3.5
    Task 7) addresses diff *selection*, not question *count*.

    The mid-of-range values (4/6/8) are locked for MVP determinism:
    the FR6 AC's "3-5 / 5-7 / 7-10" are interpreted as acceptable
    boundaries, not as required randomization. Randomness makes tests
    flaky and manual QA harder to reproduce. A future story may
    introduce complexity-aware selection within these ranges (e.g. an
    LLM tool-call or a static-analysis signal), but that is explicitly
    out of scope for Story 3.5.
    """
    if diff_lines < 100:
        return 4
    if diff_lines < 500:
        return 6
    return 8


def derive_verdict(depth: int, accuracy: int, completeness: int, insight: int) -> Verdict:
    """Map the average of four dimension scores (0-10) to a ``Verdict``.

    Deterministic — no LLM involved. The thresholds match the AC #1 spec:
      9-10 → Exceptional, 7-8 → Strong, 5-6 → Adequate,
      3-4 → Weak, 0-2 → Insufficient.

    The average is rounded to the nearest integer so ``(7+7+7+8)/4 = 7.25``
    resolves to 7 → Strong, not 7.5 → ambiguous.
    """
    avg = round((depth + accuracy + completeness + insight) / 4)
    if avg >= 9:
        return Verdict.EXCEPTIONAL
    if avg >= 7:
        return Verdict.STRONG
    if avg >= 5:
        return Verdict.ADEQUATE
    if avg >= 3:
        return Verdict.WEAK
    return Verdict.INSUFFICIENT
