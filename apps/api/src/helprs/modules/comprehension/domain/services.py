"""Comprehension domain services.

Pure, stdlib-only domain helpers. No SQLAlchemy imports, no HTTP,
no side effects — this module must stay dependency-free so the
domain-purity test keeps passing.

Story 3.3 introduces ``estimate_question_count`` — a trivial
line-count heuristic the webhook / session-creation path uses to
size a session before the first LLM call. Story 3.5 will replace it
with the role-adaptive + large-PR logic described in FR39-FR41.
"""


def estimate_question_count(diff_lines: int) -> int:
    """Size a session based on PR diff line count.

    This is the Story 3.3 minimal heuristic — deliberately dumb so
    the end-to-end flow ships first. Story 3.5 is explicitly tasked
    with replacing it; a ``TODO(story-3.5)`` marker at the call site
    in ``StartSessionHandler`` makes the seam obvious.

    Tiers:
      * ``< 100`` lines → 3 questions (small fix, short session)
      * ``100–499`` lines → 5 questions (standard PR)
      * ``>= 500`` lines → 7 questions (beefy change, more coverage)

    Negative or zero line counts fall into the smallest tier — no
    need to raise, the SSE stream handles 0-question sessions as a
    zero-iteration loop.
    """
    if diff_lines < 100:
        return 3
    if diff_lines < 500:
        return 5
    return 7
