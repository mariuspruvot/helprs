"""Comprehension application commands."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StartSessionCommand:
    """Input to ``StartSessionHandler.handle``.

    Carries exactly the PR metadata the handler needs — no dependence on
    the raw GitHub webhook payload shape. The webhook adapter is
    responsible for parsing the payload and building this command.
    """

    github_installation_id: int
    repo_full_name: str
    repo_owner: str
    repo_name: str
    pr_number: int
    pr_title: str
    pr_head_sha: str
    pr_diff_url: str
    # ``tuple`` (not ``list``) to honor ``frozen=True`` — a mutable list
    # field in a frozen dataclass still lets callers mutate labels after
    # construction. Immutable by construction keeps the command safe.
    pr_labels: tuple[str, ...]
