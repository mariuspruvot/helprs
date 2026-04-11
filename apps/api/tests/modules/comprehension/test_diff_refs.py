"""Unit tests for ``comprehension.infrastructure.diff_refs``.

P24 from story-3.3 review: the Testing Standards section of story 3.3
explicitly lists ``test_diff_refs.py``, but the file was missing from
the first dev pass. This locks the contract of the pure-string-parsing
layer that feeds the frontend's ``file_refs`` highlight behaviour
(UX-DR6) and the post-commit file-tab switch.
"""

from helprs.modules.comprehension.infrastructure.diff_refs import (
    extract_file_refs,
    parse_diff_file_paths,
)

# ----------------------------------------------------------------------
# parse_diff_file_paths
# ----------------------------------------------------------------------


class TestParseDiffFilePaths:
    def test_extracts_single_file_from_diff_git_header(self):
        diff = "diff --git a/src/foo.py b/src/foo.py\n--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1 +1 @@\n-old\n+new\n"
        assert parse_diff_file_paths(diff) == ["src/foo.py"]

    def test_preserves_order_across_multiple_files(self):
        diff = (
            "diff --git a/z.py b/z.py\n"
            "--- a/z.py\n"
            "+++ b/z.py\n"
            "@@ -1 +1 @@\n"
            "-a\n"
            "+b\n"
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            "-c\n"
            "+d\n"
        )
        # Order follows diff order, NOT alphabetical — the frontend
        # relies on this for its "first reference" lookup.
        assert parse_diff_file_paths(diff) == ["z.py", "a.py"]

    def test_extracts_both_sides_of_rename(self):
        diff = (
            "diff --git a/old/path.py b/new/path.py\n"
            "similarity index 100%\n"
            "rename from old/path.py\n"
            "rename to new/path.py\n"
        )
        paths = parse_diff_file_paths(diff)
        assert "old/path.py" in paths
        assert "new/path.py" in paths
        # First-seen order: ``a/`` side first because the ``diff --git``
        # regex captures a/ before b/.
        assert paths == ["old/path.py", "new/path.py"]

    def test_drops_dev_null_placeholders(self):
        # Added file: `a/` side is `/dev/null`, `b/` side is the real path.
        diff = (
            "diff --git a/src/new.py b/src/new.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/src/new.py\n"
            "@@ -0,0 +1 @@\n"
            "+hello\n"
        )
        paths = parse_diff_file_paths(diff)
        assert "/dev/null" not in paths
        assert "src/new.py" in paths

    def test_falls_back_to_plus_minus_headers_when_diff_git_absent(self):
        # Raw unified diff — no ``diff --git`` line. The backend must
        # still surface the path via the ``+++`` / ``---`` fallback.
        diff = "--- a/legacy/path.py\n+++ b/legacy/path.py\n@@ -1 +1 @@\n-x\n+y\n"
        assert parse_diff_file_paths(diff) == ["legacy/path.py"]

    def test_empty_diff_returns_empty_list(self):
        assert parse_diff_file_paths("") == []


# ----------------------------------------------------------------------
# extract_file_refs — P12 from story-3.3 review (word boundaries)
# ----------------------------------------------------------------------


class TestExtractFileRefs:
    def _diff_with_paths(self, *paths: str) -> str:
        blocks = []
        for p in paths:
            blocks.append(f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -1 +1 @@\n-a\n+b\n")
        return "".join(blocks)

    def test_returns_empty_when_text_is_empty(self):
        diff = self._diff_with_paths("foo.py")
        assert extract_file_refs(diff, "") == []

    def test_returns_empty_when_diff_is_empty(self):
        assert extract_file_refs("", "Check foo.py please") == []

    def test_exact_match_returned(self):
        diff = self._diff_with_paths("apps/api/foo.py")
        text = "Why did you rename apps/api/foo.py instead of splitting it?"
        assert extract_file_refs(diff, text) == ["apps/api/foo.py"]

    def test_prefix_collision_rejected(self):
        """P12: ``foo.py`` must NOT match ``foo.py.bak``. The old
        substring-based implementation returned both. Word boundaries
        treat path-component characters (word chars, dots, slashes,
        dashes) as the "path class" so one path that is a literal
        prefix of another is no longer a false positive.
        """
        diff = self._diff_with_paths("apps/api/foo.py", "apps/api/foo.py.bak")
        # Text mentions only the longer path.
        text = "Why did apps/api/foo.py.bak diverge from the main file?"
        assert extract_file_refs(diff, text) == ["apps/api/foo.py.bak"]

        # And the other direction: text mentions only the shorter path.
        text2 = "What's the intent behind apps/api/foo.py?"
        assert extract_file_refs(diff, text2) == ["apps/api/foo.py"]

    def test_path_at_end_of_sentence_matches(self):
        diff = self._diff_with_paths("src/auth.py")
        # Trailing period / comma / question mark must not defeat the
        # boundary check.
        assert extract_file_refs(diff, "Look at src/auth.py.") == ["src/auth.py"]
        assert extract_file_refs(diff, "Why src/auth.py?") == ["src/auth.py"]
        assert extract_file_refs(diff, "In src/auth.py, the assumption is...") == ["src/auth.py"]

    def test_order_follows_diff_order_not_text_order(self):
        """Two paths, both mentioned in the text, the order of the
        returned refs matches diff order. This is the invariant the
        frontend's "first reference" lookup relies on.
        """
        diff = self._diff_with_paths("first.py", "second.py")
        text = "Is second.py or first.py the right place?"  # text order reversed
        assert extract_file_refs(diff, text) == ["first.py", "second.py"]

    def test_path_not_in_text_is_dropped(self):
        diff = self._diff_with_paths("a.py", "b.py")
        text = "This question is about general architecture."
        assert extract_file_refs(diff, text) == []

    def test_no_substring_inside_unrelated_word(self):
        """Path like ``bar.py`` must not match text like ``bar.py`` being
        embedded inside ``foobar.python`` or ``bar.pyramid``.
        """
        diff = self._diff_with_paths("bar.py")
        assert extract_file_refs(diff, "import bar.pyramid somewhere") == []
        assert extract_file_refs(diff, "foobar.python modules") == []
        assert extract_file_refs(diff, "bar.py") == ["bar.py"]


# Story 3.4: code-link detection (``path:line`` → clickable) is now a
# frontend-only concern. The backend no longer parses feedback text;
# ``ChatMessage.tsx`` walks the rendered markdown and matches inline
# code refs against ``DiffFilePathsContext``. See code-review decision
# D2 in the story file for the rationale.
