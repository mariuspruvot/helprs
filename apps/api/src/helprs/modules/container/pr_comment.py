"""Score card extraction and PR comment formatting for challenge-me sessions."""

import re
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.modules.container.models import SessionEvent

logger = structlog.get_logger()

_RESULTS_PATTERN = re.compile(
    r"---\s*\n\s*\n##\s+Results\b(.*?)^---\s*$",
    re.DOTALL | re.MULTILINE,
)


async def extract_score_card(session_id: UUID, db: AsyncSession) -> str | None:
    """Extract the score card markdown from persisted session events.

    Queries the last ``result`` event for the session and extracts the
    ``## Results`` section delimited by ``---`` markers (as defined in
    ``skills/challenge-me/CLAUDE.md``).
    """
    result = await db.execute(
        select(SessionEvent.data)
        .where(
            SessionEvent.session_id == session_id,
            SessionEvent.data["type"].astext == "result",
        )
        .order_by(SessionEvent.event_id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    result_text = row.get("result")
    if not result_text or not isinstance(result_text, str):
        return None

    match = _RESULTS_PATTERN.search(result_text)
    if not match:
        return None

    return f"## Results{match.group(1).rstrip()}"


def format_pr_comment(
    score_card: str,
    session_url: str,
) -> str:
    """Format the score card as a GitHub PR comment."""
    return (
        f"### helPRs Challenge-Me Results\n\n"
        f"{score_card}\n\n"
        f"<details>\n"
        f"<summary>View session</summary>\n\n"
        f"[Open full Q&A session]({session_url})\n\n"
        f"---\n"
        f"*Posted by [helPRs](https://github.com/apps/helprs)*\n"
        f"</details>\n"
    )


def build_session_url(
    app_base_url: str,
    installation_id: UUID,
    repo_full_name: str,
    pr_number: int,
) -> str:
    """Build the frontend session URL for a PR."""
    return f"{app_base_url}/session/{installation_id}/{repo_full_name}/{pr_number}"
