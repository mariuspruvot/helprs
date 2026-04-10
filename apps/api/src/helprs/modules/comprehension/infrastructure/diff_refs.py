"""Extract referenced file paths from a Socratic question text.

Story 3.3: after a question is generated, the SSE endpoint runs a
simple substring match against the set of files in the unified diff
to populate ``QuestionPayload.file_refs``. The frontend uses these to
highlight + switch the active diff tab when the question mentions a
file (UX-DR6).

Keep this separate from ``github_diff.py`` on purpose: the latter is
a GitHub REST client (I/O); this is pure string parsing. Mixing them
muddies the single-responsibility line and makes unit testing the
parser harder.

Smarter extraction via LLM tool-calls is deferred to Story 3.4/3.5.
"""

import re

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

    Matching is a plain substring check — cheap, unambiguous, and
    good enough for UX-DR6's "highlight if the question mentions a
    file" behaviour. A future Story 3.5 may replace this with an
    LLM-side tool-call that emits references structurally.

    Order follows diff order so the frontend's "first reference"
    lookup is deterministic.
    """
    if not text or not diff:
        return []
    paths = parse_diff_file_paths(diff)
    return [p for p in paths if p in text]
