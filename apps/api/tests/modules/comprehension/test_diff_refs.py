"""Unit tests for ``comprehension.infrastructure.diff_refs``.

P24 from story-3.3 review: the Testing Standards section of story 3.3
explicitly lists ``test_diff_refs.py``, but the file was missing from
the first dev pass. This locks the contract of the pure-string-parsing
layer that feeds the frontend's ``file_refs`` highlight behaviour
(UX-DR6) and the post-commit file-tab switch.
"""

from helprs.modules.comprehension.infrastructure.diff_refs import (
    _LARGE_PR_FILE_LINE_BUDGET,
    _LARGE_PR_LINE_THRESHOLD,
    _LARGE_PR_TOTAL_LINE_BUDGET,
    FileChangeStats,
    compute_file_stats,
    extract_file_refs,
    parse_diff_file_paths,
    select_and_rank_files,
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


# ----------------------------------------------------------------------
# Story 3.5: compute_file_stats + select_and_rank_files
# ----------------------------------------------------------------------


def _make_file_section(
    path: str,
    *,
    additions: int,
    deletions: int,
) -> str:
    """Build a synthetic unified-diff section with the requested
    addition/deletion counts. ``+++``/``---`` headers are added but
    NOT counted as content lines (per compute_file_stats contract).
    """
    lines = [
        f"diff --git a/{path} b/{path}",
        f"--- a/{path}",
        f"+++ b/{path}",
        "@@ -1 +1 @@",
    ]
    for i in range(additions):
        lines.append(f"+added_line_{i}")
    for i in range(deletions):
        lines.append(f"-deleted_line_{i}")
    return "\n".join(lines)


class TestComputeFileStats:
    def test_single_file_counts_additions_and_deletions(self):
        diff = _make_file_section("src/foo.py", additions=3, deletions=2)
        stats = compute_file_stats(diff)
        assert stats == [FileChangeStats(path="src/foo.py", additions=3, deletions=2)]

    def test_multiple_files_returned_in_diff_order(self):
        diff = (
            _make_file_section("src/z.py", additions=5, deletions=1)
            + "\n"
            + _make_file_section("src/a.py", additions=2, deletions=4)
        )
        stats = compute_file_stats(diff)
        assert [s.path for s in stats] == ["src/z.py", "src/a.py"]
        assert stats[0].additions == 5
        assert stats[0].deletions == 1
        assert stats[1].additions == 2
        assert stats[1].deletions == 4

    def test_rename_with_no_content_change_returns_zeros(self):
        diff = "diff --git a/old.py b/new.py\nsimilarity index 100%\nrename from old.py\nrename to new.py\n"
        stats = compute_file_stats(diff)
        # The ``b/`` path wins (destination) for renames.
        assert stats == [FileChangeStats(path="new.py", additions=0, deletions=0)]

    def test_plus_plus_and_minus_minus_headers_not_counted_as_content(self):
        diff = _make_file_section("src/foo.py", additions=0, deletions=0)
        stats = compute_file_stats(diff)
        # Even though the section has ``+++`` and ``---`` header lines,
        # they are not content and must not show up in the counts.
        assert stats == [FileChangeStats(path="src/foo.py", additions=0, deletions=0)]

    def test_content_lines_literally_starting_with_plus_plus_plus_are_counted(self):
        """Story 3.5 code-review patch (P7): a content line that literally
        starts with ``+++`` (e.g. C macro, Markdown horizontal rule,
        ASCII separator) was silently dropped by the naive
        ``startswith("+++")`` header filter. The new header-state
        tracker only treats the first two ``--- a/`` / ``+++ b/``
        / ``/dev/null`` lines per section as headers.
        """
        diff = (
            "diff --git a/src/macros.c b/src/macros.c\n"
            "--- a/src/macros.c\n"
            "+++ b/src/macros.c\n"
            "@@ -1,2 +1,4 @@\n"
            " existing\n"
            "+++DEFINE FOO\n"
            "+++DEFINE BAR\n"
            "---deleted one\n"
            "---deleted two\n"
        )
        stats = compute_file_stats(diff)
        # Two additions + two deletions that were previously lost.
        assert stats == [FileChangeStats(path="src/macros.c", additions=2, deletions=2)]

    def test_total_lines_property_sums_additions_and_deletions(self):
        entry = FileChangeStats(path="x", additions=7, deletions=3)
        assert entry.total_lines == 10

    def test_empty_diff_returns_empty_list(self):
        assert compute_file_stats("") == []


class TestSelectAndRankFiles:
    def test_small_pr_passes_through_unchanged(self):
        """Total < threshold → returned diff byte-for-byte equal to input,
        stats list matches compute_file_stats output (AC #14).

        Story 3.5 code-review patch (P2): the original dev pass weakened
        this assertion to ``isinstance(result_diff, str)`` because the
        helper did not short-circuit below threshold. Helper now early-
        returns; assertion restored to spec wording.
        """
        diff = _make_file_section("a.py", additions=10, deletions=5)
        stats = compute_file_stats(diff)
        assert sum(s.total_lines for s in stats) < _LARGE_PR_LINE_THRESHOLD

        result_diff, result_stats = select_and_rank_files(diff, stats=stats)
        assert result_stats == stats
        assert result_diff == diff  # byte-for-byte equality per AC #14

    def test_three_file_pass_through_below_threshold(self):
        """Story 3.5 code-review patch (P2 / AC #14 first sub-case):
        a 3-file diff (1500/400/50) totaling 1950 lines — BELOW the 2000
        threshold — must pass through byte-for-byte.
        """
        diff = (
            _make_file_section("dominant.py", additions=1500, deletions=0)
            + "\n"
            + _make_file_section("moderate.py", additions=400, deletions=0)
            + "\n"
            + _make_file_section("small.py", additions=50, deletions=0)
        )
        stats = compute_file_stats(diff)
        total = sum(s.total_lines for s in stats)
        assert total == 1950
        assert total < _LARGE_PR_LINE_THRESHOLD

        result_diff, result_stats = select_and_rank_files(diff, stats=stats)
        assert result_diff == diff
        assert len(result_stats) == 3

    def test_small_pr_below_threshold_via_sse_guard_semantics(self):
        """Integration-style: the sse.stream_session callsite only calls
        ``select_and_rank_files`` when ``total_lines >= threshold``. This
        test exercises a just-below-threshold diff to confirm the helper
        still produces a deterministic output when called.
        """
        diff = _make_file_section("a.py", additions=1500, deletions=400)
        result_diff, result_stats = select_and_rank_files(diff)
        # 1900 total lines — under the 2000 threshold. The helper still
        # returns a valid (diff, stats) pair without crashing.
        assert len(result_stats) == 1
        assert result_stats[0].total_lines == 1900
        assert "a.py" in result_diff

    def test_huge_pr_ranks_files_by_total_lines_desc(self):
        """Story 3.5 code-review patch (P3): renamed from
        ``test_huge_pr_ranks_and_elides_smallest_files`` — the original
        name was a lie because the 2500-line fixture is well under the
        40_000 total budget, so no file is actually elided. AC #14 asks
        for an "excludes the smallest" assertion at this shape but the
        implemented thresholds cannot elide at 2500 total lines; the
        spec-implementation drift is noted in the story's Review
        Findings section and in memory. Actual elision coverage lives
        in ``test_stats_list_always_full_regardless_of_ranking`` and
        ``test_cumulative_budget_is_honored_across_retained_files``
        below.
        """
        diff = (
            _make_file_section("dominant.py", additions=1500, deletions=0)
            + "\n"
            + _make_file_section("moderate.py", additions=800, deletions=0)
            + "\n"
            + _make_file_section("small.py", additions=200, deletions=0)
        )
        stats = compute_file_stats(diff)
        assert sum(s.total_lines for s in stats) == 2500
        assert sum(s.total_lines for s in stats) >= _LARGE_PR_LINE_THRESHOLD

        ranked_diff, ranked_stats = select_and_rank_files(diff, stats=stats)

        # AC #7: stats list is the FULL unranked list (one entry per
        # file in the original diff). Under the current budget
        # (40_000 total, 1500 per file), all three files fit — verify
        # ranking ORDER, not elision.
        assert len(ranked_stats) == 3
        assert {s.path for s in ranked_stats} == {"dominant.py", "moderate.py", "small.py"}
        # Dominant file appears first in the reconstructed output
        # (ranked by total_lines desc).
        assert ranked_diff.index("dominant.py") < ranked_diff.index("moderate.py")
        assert ranked_diff.index("moderate.py") < ranked_diff.index("small.py")

    def test_stats_list_always_full_regardless_of_ranking(self):
        """AC #14 'test_stats_list_always_full': the returned stats list
        must include one entry per file in the original diff even when
        files get elided.
        """
        # Synthesize a diff where cumulative lines force an elision.
        files = [(f"f{i}.py", 20_000, 0) for i in range(3)]
        diff_parts = [_make_file_section(path, additions=a, deletions=d) for path, a, d in files]
        diff = "\n".join(diff_parts)
        assert sum(a + d for _, a, d in files) == 60_000  # above total budget

        ranked_diff, ranked_stats = select_and_rank_files(diff)
        # Full list of 3 files always returned in the stats.
        assert len(ranked_stats) == 3
        # At least one file elided because cumulative > _LARGE_PR_TOTAL_LINE_BUDGET
        assert "<!-- elided" in ranked_diff

    def test_cumulative_budget_is_honored_across_retained_files(self):
        # Five files, each 10_000 lines → total 50_000 > 40_000 budget.
        files = [(f"big{i}.py", 10_000, 0) for i in range(5)]
        diff = "\n".join(_make_file_section(p, additions=a, deletions=d) for p, a, d in files)

        ranked_diff, ranked_stats = select_and_rank_files(diff)

        # Stats list still has all 5 files.
        assert len(ranked_stats) == 5
        # Elision block present — means ranking actually dropped files.
        assert "<!-- elided" in ranked_diff
        # The number of retained diff sections must be bounded so
        # cumulative retained ≤ budget. Each retained section has its
        # path in the body; count them.
        retained_count = sum(1 for i in range(5) if f"diff --git a/big{i}.py" in ranked_diff)
        assert retained_count * 10_000 <= _LARGE_PR_TOTAL_LINE_BUDGET

    def test_single_file_exceeding_total_budget_is_truncated_not_dropped(self):
        """Edge case: one file larger than the full cumulative budget
        must still appear (truncated), not silently dropped.
        """
        diff = _make_file_section("huge.py", additions=60_000, deletions=0)
        ranked_diff, ranked_stats = select_and_rank_files(diff)

        assert len(ranked_stats) == 1
        assert ranked_stats[0].path == "huge.py"
        # Truncation marker appears in the output.
        assert "truncated file huge.py" in ranked_diff
        assert f"{_LARGE_PR_FILE_LINE_BUDGET} lines" in ranked_diff

    def test_elision_summary_names_excluded_files_with_stats(self):
        files = [(f"big{i}.py", 15_000, 0) for i in range(4)]
        diff = "\n".join(_make_file_section(p, additions=a, deletions=d) for p, a, d in files)
        ranked_diff, _ = select_and_rank_files(diff)
        # Each elided file's HTML-comment line carries its path + stats.
        for i in range(4):
            if f"diff --git a/big{i}.py" not in ranked_diff:
                assert f"big{i}.py (+15000 / -0)" in ranked_diff

    def test_empty_diff_returns_empty(self):
        result_diff, result_stats = select_and_rank_files("")
        assert result_diff == ""
        assert result_stats == []
