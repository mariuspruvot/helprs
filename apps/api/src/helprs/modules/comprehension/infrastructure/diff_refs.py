"""Extract referenced file paths from a Socratic question text.

Story 3.3: after a question is generated, the SSE endpoint runs a
simple substring match against the set of files in the unified diff
to populate ``QuestionPayload.file_refs``. The frontend uses these to
highlight + switch the active diff tab when the question mentions a
file (UX-DR6).

Story 3.5 adds per-file line-change statistics (``FileChangeStats`` +
``compute_file_stats``) and a large-PR ranking helper
(``select_and_rank_files``). These are used by
``PydanticAILLMProvider`` to render a "Per-file line stats" block in
the prompt and to trim huge diffs down to the most relevant files
before sending to the LLM.

Keep this separate from ``github_diff.py`` on purpose: the latter is
a GitHub REST client (I/O); this is pure string parsing. Mixing them
muddies the single-responsibility line and makes unit testing the
parser harder.
"""

import re
from dataclasses import dataclass

# ``diff --git a/path/to/file b/path/to/file`` is the canonical header.
# ``+++ b/<path>`` / ``--- a/<path>`` work too. We match ``diff --git``
# first because it covers rename / copy cases where ``+++ b/`` alone
# would point at the destination.
_DIFF_GIT_LINE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)
_PLUS_HEADER = re.compile(r"^\+\+\+ b/(.+?)$", re.MULTILINE)
_MINUS_HEADER = re.compile(r"^--- a/(.+?)$", re.MULTILINE)

_DEV_NULL = "/dev/null"


def parse_diff_file_paths(diff: str) -> list[str]:
    """Return the ordered, de-duplicated list of file paths in the diff.

    Preserves first-seen order so ``file_refs`` and the frontend diff
    viewer agree on which file is "first". Drops ``/dev/null`` (added
    or deleted file placeholders).
    """
    seen: set[str] = set()
    ordered: list[str] = []

    for match in _DIFF_GIT_LINE.finditer(diff):
        for path in match.groups():
            if path and path != _DEV_NULL and path not in seen:
                seen.add(path)
                ordered.append(path)

    # Fall back on ``+++``/``---`` headers for diffs that don't carry
    # ``diff --git`` (rare but possible with some tooling).
    for match in _PLUS_HEADER.finditer(diff):
        path = match.group(1).strip()
        if path and path != _DEV_NULL and path not in seen:
            seen.add(path)
            ordered.append(path)
    for match in _MINUS_HEADER.finditer(diff):
        path = match.group(1).strip()
        if path and path != _DEV_NULL and path not in seen:
            seen.add(path)
            ordered.append(path)

    return ordered


def extract_file_refs(diff: str, text: str) -> list[str]:
    """Return the list of file paths from ``diff`` mentioned in ``text``.

    Matching uses path-character-aware boundaries so that:

    * ``foo.py`` does NOT match a question mentioning ``foo.py.bak``
      (the trailing ``.bak`` would extend the path — a separate file)
    * ``foo.py`` DOES match a sentence ending in ``foo.py.`` (the
      trailing period is sentence punctuation, not a path extension)
    * ``src/foo.ts`` does NOT accidentally match a bare ``foo.ts`` in
      some other directory
    * ``bar.py`` does NOT match ``bar.pyramid`` (``r`` extends the
      name into a different identifier)

    Order follows diff order so the frontend's "first reference"
    lookup is deterministic. A future Story 3.5 may replace this
    with an LLM-side tool-call that emits references structurally.
    """
    if not text or not diff:
        return []
    paths = parse_diff_file_paths(diff)
    refs: list[str] = []
    for path in paths:
        # Left boundary ``(?<![\w/.-])``: the position must not be
        # preceded by a path-component character (including ``.`` and
        # ``/``) so we don't match the tail of a longer path.
        #
        # Right boundary ``(?![\w/-])``: the position must not be
        # followed by a word/slash/dash character (extending the name
        # or adding another path segment).
        #
        # Right boundary ``(?!\.\w)``: the position must not be
        # followed by ``.<wordchar>`` — this is the key asymmetry that
        # lets ``foo.py`` match ``foo.py.`` (sentence period) but NOT
        # ``foo.py.bak`` (path extension).
        pattern = rf"(?<![\w/.-]){re.escape(path)}(?![\w/-])(?!\.\w)"
        if re.search(pattern, text):
            refs.append(path)
    return refs


# ----------------------------------------------------------------------
# Story 3.5: per-file line-change stats + large-PR ranking
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FileChangeStats:
    """Per-file addition/deletion counts parsed from a unified diff.

    Lives in ``diff_refs.py`` (the authoritative parser) and is
    imported by ``agents.py`` as the prompt-stats DTO. Story 3.5
    (AC #7 / Task 3.1) deliberately shares one class instead of
    duplicating it so the prompt stays faithful to what the parser
    saw.
    """

    path: str
    additions: int
    deletions: int

    @property
    def total_lines(self) -> int:
        return self.additions + self.deletions


# Story 3.5 (AC #7, FR11) — large-PR tuning constants. Kept at module
# level rather than in ``core/config.py``: these are algorithm-tuning
# parameters, not runtime-configurable settings. Promote them to
# settings only if a real operational need arises.
_LARGE_PR_LINE_THRESHOLD = 2000
_LARGE_PR_FILE_LINE_BUDGET = 1500  # single-file content cap after ranking
_LARGE_PR_TOTAL_LINE_BUDGET = 40_000  # cumulative cap across retained files


def compute_file_stats(diff: str) -> list[FileChangeStats]:
    """Parse a unified diff and return per-file addition/deletion counts.

    Walks the diff once, tracking the current file via ``diff --git``
    headers. For each file section, counts lines starting with ``+``
    (additions) and ``-`` (deletions), skipping the ``+++``/``---``
    header lines (which belong to the section header, not the content).

    Order follows diff order — the same order ``parse_diff_file_paths``
    emits, so downstream "first reference" lookups stay consistent.
    A file with only ``+++``/``---`` headers (e.g. a rename with no
    content change) yields ``(0, 0)``. ``/dev/null`` placeholders
    (added/deleted file markers) are dropped.
    """
    stats: list[FileChangeStats] = []
    current_path: str | None = None
    current_additions = 0
    current_deletions = 0
    # Story 3.5 code-review patch (P7): a unified-diff section has
    # exactly two header lines (``--- a/<path>`` + ``+++ b/<path>``)
    # right after the ``diff --git`` line and before any hunks. The
    # original implementation used ``line.startswith("+++")`` /
    # ``line.startswith("---")`` to detect them, which silently
    # dropped CONTENT lines literally starting with ``+++`` / ``---``
    # (C macros ``+++DEFINE``, Markdown horizontal rules, ASCII
    # separators). Track how many header lines we've already
    # consumed for the current section instead: real git headers
    # are prefixed with a slash (``--- a/`` / ``+++ b/``) OR the
    # ``/dev/null`` sentinel, which is distinguishable from content.
    headers_seen = 0

    def flush() -> None:
        nonlocal current_path, current_additions, current_deletions, headers_seen
        if current_path is not None and current_path != _DEV_NULL:
            stats.append(
                FileChangeStats(
                    path=current_path,
                    additions=current_additions,
                    deletions=current_deletions,
                )
            )
        current_path = None
        current_additions = 0
        current_deletions = 0
        headers_seen = 0

    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            # New file section — flush the previous file first.
            flush()
            # Parse ``diff --git a/<path> b/<path>`` and prefer the ``b/``
            # path (destination) so renames are attributed to their new
            # location. Fallback to the ``a/`` path if ``b/`` is absent.
            match = _DIFF_GIT_LINE.match(line)
            if match:
                current_path = match.group(2) or match.group(1)
            continue
        if current_path is None:
            # Preamble or unexpected content before the first header.
            continue
        # Story 3.5 P7: detect the two real section headers via their
        # canonical shape — ``--- a/...`` / ``+++ b/...`` / ``/dev/null``
        # variants — and only for the first two header slots per
        # section, so a content line like ``+++DEFINE`` that happens
        # to appear inside a hunk is still counted as an addition.
        if headers_seen < 2 and (
            line.startswith("--- a/") or line.startswith("+++ b/") or line == "--- /dev/null" or line == "+++ /dev/null"
        ):
            headers_seen += 1
            continue
        if line.startswith("+"):
            current_additions += 1
        elif line.startswith("-"):
            current_deletions += 1
    # Flush the final file at EOF.
    flush()
    return stats


def _slice_file_sections(diff: str) -> dict[str, str]:
    """Split a diff into per-file section text blocks.

    Each block starts at the ``diff --git`` header and ends just before
    the next header (or at EOF). Used by ``select_and_rank_files`` to
    reconstruct a ranked subset of the diff while preserving the full
    section content for retained files verbatim.
    """
    sections: dict[str, str] = {}
    lines = diff.split("\n")
    current_path: str | None = None
    current_buf: list[str] = []
    for line in lines:
        if line.startswith("diff --git "):
            if current_path is not None and current_path != _DEV_NULL:
                sections[current_path] = "\n".join(current_buf)
            match = _DIFF_GIT_LINE.match(line)
            current_path = (match.group(2) or match.group(1)) if match else None
            current_buf = [line]
        else:
            current_buf.append(line)
    if current_path is not None and current_path != _DEV_NULL:
        sections[current_path] = "\n".join(current_buf)
    return sections


def select_and_rank_files(
    diff: str,
    stats: list[FileChangeStats] | None = None,
) -> tuple[str, list[FileChangeStats]]:
    """Rank files in ``diff`` by total_lines desc and return a trimmed diff.

    If ``stats`` is ``None`` it is computed via ``compute_file_stats``.
    Files are ranked largest-change-first (stable on ties — diff order
    wins) and walked into the output buffer until the next file would
    exceed ``_LARGE_PR_TOTAL_LINE_BUDGET``. Files past that point are
    elided; their paths + stats are appended as an HTML-comment summary
    block so the LLM knows what it is NOT seeing.

    **Edge case:** if the single largest file exceeds
    ``_LARGE_PR_TOTAL_LINE_BUDGET`` on its own, include the first
    ``_LARGE_PR_FILE_LINE_BUDGET`` lines of its section anyway — silently
    dropping everything would starve the LLM of context entirely.

    Returns ``(ranked_diff_text, all_stats)`` — the returned stats list
    is the **full unranked list** (one entry per file in the original
    diff), so callers can render per-file stats for every file even
    though the diff body contains only the retained subset.
    """
    if stats is None:
        stats = compute_file_stats(diff)

    if not stats:
        return diff, stats

    # Story 3.5 code-review patch (P2): below-threshold PRs must return
    # byte-for-byte equal to the input (AC #14). The reconstruction via
    # ``_slice_file_sections`` + ``"\n".join(retained_buf)`` is *almost*
    # idempotent but drops whitespace edge cases for pathological
    # diffs, so short-circuit explicitly when nothing needs ranking.
    if sum(s.total_lines for s in stats) < _LARGE_PR_LINE_THRESHOLD:
        return diff, stats

    sections = _slice_file_sections(diff)

    ranked = sorted(
        enumerate(stats),
        key=lambda item: (-item[1].total_lines, item[0]),
    )
    ranked_stats = [entry for _, entry in ranked]

    retained_paths: list[str] = []
    retained_buf: list[str] = []
    cumulative = 0
    for entry in ranked_stats:
        section = sections.get(entry.path)
        if section is None:
            continue
        total = entry.total_lines
        if retained_paths and cumulative + total > _LARGE_PR_TOTAL_LINE_BUDGET:
            # Budget would overflow if we added this file — stop.
            break
        if not retained_paths and total > _LARGE_PR_TOTAL_LINE_BUDGET:
            # Single-file-overflow edge case: truncate its section to
            # ``_LARGE_PR_FILE_LINE_BUDGET`` lines so the LLM at least
            # sees the top of the dominant file.
            truncated_lines = section.split("\n")[:_LARGE_PR_FILE_LINE_BUDGET]
            truncated_lines.append(f"<!-- truncated file {entry.path} at {_LARGE_PR_FILE_LINE_BUDGET} lines -->")
            retained_buf.append("\n".join(truncated_lines))
            retained_paths.append(entry.path)
            cumulative += _LARGE_PR_FILE_LINE_BUDGET
            continue
        retained_buf.append(section)
        retained_paths.append(entry.path)
        cumulative += total

    retained_set = set(retained_paths)
    elided = [entry for entry in ranked_stats if entry.path not in retained_set]
    if elided:
        summary_lines = [f"<!-- elided {len(elided)} files -->"]
        for entry in elided:
            summary_lines.append(f"<!-- - {entry.path} (+{entry.additions} / -{entry.deletions}) -->")
        retained_buf.append("\n".join(summary_lines))

    ranked_diff = "\n".join(retained_buf)
    return ranked_diff, stats
