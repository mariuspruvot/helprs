#!/bin/bash
# -E propagates the ERR trap into functions and subshells; without it a failure
# inside a helper exits silently.
set -Eeuo pipefail

# Clean shutdown on SIGTERM/SIGINT (docker stop).
# Do NOT use `kill 0` — it sends SIGTERM to bash's own process group while
# inside the trap handler, causing exit code 139 instead of 0. Docker kills
# all remaining processes when PID 1 exits, so explicit child cleanup is
# unnecessary.
cleanup() {
  exit 0
}
trap cleanup SIGTERM SIGINT

# Emit a structured error event to stdout so the SSE pipeline relays it
# to the frontend before the container exits.
emit_error() {
  local msg="$1"
  # Escape backslashes and double quotes for JSON safety
  msg="${msg//\\/\\\\}"
  msg="${msg//\"/\\\"}"
  printf '{"type":"error","error":{"message":"%s"}}\n' "$msg"
}

# Every setup failure below is meant to be reported through emit_error, but
# `set -e` aborts on the first unchecked non-zero status without running one.
# This trap is the backstop so no setup path can exit silently and leave the
# frontend with a dead session and no reason. It is cleared once setup is done.
trap 'emit_error "Container setup failed unexpectedly at line ${LINENO}."; exit 1' ERR

# Replace every literal occurrence of a marker with a literal value, in place.
#
# Deliberately not `sed`: sed builds an expression *from the data*, so a value
# containing the delimiter can close the s command and start another one --
# and GNU sed's `e` command then executes a shell. PR titles are attacker-
# controlled, which made that a remote code execution path. Here the value
# reaches awk through the environment (never -v, which expands backslash
# escapes) and is only ever used with index()/substr(), so no byte of it is
# parsed as a pattern or as code.
substitute_inline() {
  local marker="$1" value="$2"
  MARKER="$marker" VALUE="$value" awk '
    BEGIN { m = ENVIRON["MARKER"]; v = ENVIRON["VALUE"]; ml = length(m) }
    {
      out = ""
      while ((p = index($0, m)) > 0) {
        out = out substr($0, 1, p - 1) v
        $0 = substr($0, p + ml)
      }
      print out $0
    }
  ' "$PROMPT_FILE" > /tmp/prompt_tmp.md
  mv /tmp/prompt_tmp.md "$PROMPT_FILE"
}

# gh CLI auto-detects GITHUB_TOKEN env var -- no explicit login needed.
gh auth status > /dev/null 2>&1 || {
  emit_error "GitHub authentication failed. The token may be expired or invalid."
  exit 1
}

# ---------------------------------------------------------------------------
# Parallel I/O: clone, metadata fetch, and diff fetch run concurrently.
# Metadata/diff use -R flag to hit the GitHub API directly — no local repo
# needed, so they can overlap with the clone.
# ---------------------------------------------------------------------------

gh repo clone "$REPO_FULL_NAME" /workspace -- --depth=1 &
clone_pid=$!

gh pr view "$PR_NUMBER" -R "$REPO_FULL_NAME" \
    --json title,author,body,files > /tmp/pr_meta.json &
meta_pid=$!

gh pr diff "$PR_NUMBER" -R "$REPO_FULL_NAME" > /tmp/pr_diff.txt &
diff_pid=$!

# Wait for each job individually — background failures don't trigger set -e.
wait $clone_pid || {
  emit_error "Failed to clone repository ${REPO_FULL_NAME}. It may have been deleted or made private."
  exit 1
}
wait $meta_pid || {
  emit_error "Failed to fetch PR #${PR_NUMBER} metadata from GitHub API."
  exit 1
}
wait $diff_pid || {
  emit_error "Failed to fetch PR #${PR_NUMBER} diff from GitHub API."
  exit 1
}

# Checkout PR branch (requires completed clone)
cd /workspace
gh pr checkout "$PR_NUMBER" --detach || {
  emit_error "Failed to checkout PR #${PR_NUMBER}. The branch may have been deleted after the PR was merged."
  exit 1
}

# Parse metadata from the single combined API response
PR_TITLE=$(jq -r '.title' /tmp/pr_meta.json)
PR_AUTHOR=$(jq -r '.author.login' /tmp/pr_meta.json)
PR_DESCRIPTION=$(jq -r '.body // "No description provided."' /tmp/pr_meta.json)
FILE_LIST=$(jq -r '.files[].path' /tmp/pr_meta.json)

# Build the prompt file from template + PR context.
# Write to a file instead of holding in a shell variable to avoid
# "Argument list too long" on large PRs (ARG_MAX ~2MB).
PROMPT_FILE=/tmp/prompt.md
{
  cat "/skills/$SKILL_NAME/prompt.md"
} > "$PROMPT_FILE"

# Short fields substituted inline; they can appear mid-line in a template.
substitute_inline "{{PR_NUMBER}}" "$PR_NUMBER"
substitute_inline "{{PR_TITLE}}" "$PR_TITLE"
substitute_inline "{{PR_AUTHOR}}" "$PR_AUTHOR"

# Large fields go through files rather than shell variables to stay clear of
# ARG_MAX on big PRs. printf rather than echo: bash's builtin echo swallows a
# leading -n/-e/-E, which a PR description can legitimately start with.
printf '%s\n' "$PR_DESCRIPTION" > /tmp/pr_description.txt
printf '%s\n' "$FILE_LIST" > /tmp/pr_filelist.txt

# For each large placeholder: replace the line containing it with the file contents.
# Using awk because sed r-command can't replace inline — it only appends.
for placeholder_pair in \
    "{{PR_DESCRIPTION}}:/tmp/pr_description.txt" \
    "{{FILE_LIST}}:/tmp/pr_filelist.txt" \
    "{{PR_DIFF}}:/tmp/pr_diff.txt"; do
  marker="${placeholder_pair%%:*}"
  file="${placeholder_pair##*:}"
  if grep -qF "$marker" "$PROMPT_FILE" && [ -f "$file" ]; then
    awk -v marker="$marker" -v file="$file" '
      index($0, marker) {
        while ((getline line < file) > 0) print line
        close(file)
        next
      }
      { print }
    ' "$PROMPT_FILE" > /tmp/prompt_tmp.md
    mv /tmp/prompt_tmp.md "$PROMPT_FILE"
  fi
done

# Setup is done. Past this point a non-zero status is a skill run ending
# badly, not a setup failure, and the claude invocations handle their own
# (`|| true`), so the backstop would only produce misleading errors.
trap - ERR

# ---------------------------------------------------------------------------
# Multi-turn conversation via per-turn invocations
#
# Claude Code CLI in --input-format stream-json mode exits after completing
# each conversation turn (emits result event, then exit 0). It does NOT wait
# for the next user message on stdin.
#
# Fix: run one `claude -p` per turn. The first turn sends the initial skill
# prompt. Subsequent turns read from a FIFO and use `--continue` to resume
# the conversation with full context from Claude's local session store.
# ---------------------------------------------------------------------------

# Create FIFO early so docker exec writes never fail with "No such file".
FIFO=/tmp/claude-input
mkfifo "$FIFO"
# Keep a persistent fd so the FIFO reader never sees EOF between individual
# docker-exec writes. Uses read-write mode (<>) because opening a FIFO with
# O_WRONLY (>) blocks until a reader exists -- but our reader starts later.
# O_RDWR never blocks on FIFOs. Fd closes when the container is stopped.
exec 3<>"$FIFO"

# First turn: initial skill prompt (one-shot, creates the conversation)
# The full prompt is written to a file to avoid ARG_MAX on large PRs.
# We pass a short bootstrap prompt that tells Claude to read the file.
claude -p "Read the file /tmp/prompt.md and follow its instructions exactly. It contains a skill prompt with PR context. Start immediately." \
    --output-format stream-json \
    --verbose \
    --dangerously-skip-permissions \
    --max-turns 30 || true

# Subsequent turns: read user messages from FIFO, continue conversation.
# Each line is the raw user message content (newline-terminated).
while IFS= read -r line; do
    [ -z "$line" ] && continue
    claude -c -p "$line" \
        --output-format stream-json \
        --verbose \
        --dangerously-skip-permissions \
        --max-turns 30 || true
done < "$FIFO"
