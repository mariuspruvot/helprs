"""Rendering a finished session as a GitHub PR comment.

Built from the validated ``Scorecard``, not from the markdown the skill
writes for the live stream. Two extractors used to coexist -- a validated
JSON parser feeding the dashboard and an unvalidated regex over the markdown
feeding this comment -- so one session could be scored in one place and
silently uncommented in the other. There is one machine-readable source now,
and this module no longer runs its own SQL over the events table.
"""

from uuid import UUID

from helprs.modules.container.scorecard import MAX_DIMENSION_SCORE, Scorecard

_BAR_WIDTH = 10


def _score_bar(score: float) -> str:
    filled = round(score * _BAR_WIDTH / MAX_DIMENSION_SCORE)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


def _dimensions_table(scorecard: Scorecard) -> str:
    rows = "\n".join(
        f"| {name.replace('_', ' ').title()} | {score:g} / {MAX_DIMENSION_SCORE} |"
        for name, score in scorecard.dimensions.items()
    )
    return f"| Dimension | Score |\n|-----------|-------|\n{rows}"


def format_pr_comment(scorecard: Scorecard, session_url: str) -> str:
    """Render the scorecard as the comment body."""
    overall = scorecard.overall_score
    sections = [
        "### helPRs Challenge-Me Results",
        "",
        f"**Score: {overall:.1f} / {MAX_DIMENSION_SCORE}**  {_score_bar(overall)}",
        "",
        _dimensions_table(scorecard),
        "",
        scorecard.summary,
    ]

    if scorecard.highlights:
        sections += ["", "**Highlights**", *(f"- {item}" for item in scorecard.highlights)]

    sections += [
        "",
        "<details>",
        "<summary>View session</summary>",
        "",
        f"[Open full Q&A session]({session_url})",
        "",
        "---",
        "*Posted by [helPRs](https://github.com/apps/helprs)*",
        "</details>",
        "",
    ]
    return "\n".join(sections)


def build_session_url(
    app_base_url: str,
    installation_id: UUID,
    repo_full_name: str,
    pr_number: int,
) -> str:
    """Build the frontend session URL for a PR."""
    return f"{app_base_url}/session/{installation_id}/{repo_full_name}/{pr_number}"
