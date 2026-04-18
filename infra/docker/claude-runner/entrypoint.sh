#!/bin/bash
set -euo pipefail

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
gh pr checkout "$PR_NUMBER" || {
  emit_error "Failed to checkout PR #${PR_NUMBER}. The branch may have been deleted after the PR was merged."
  exit 1
}

# Parse metadata from the single combined API response
PR_TITLE=$(jq -r '.title' /tmp/pr_meta.json)
PR_AUTHOR=$(jq -r '.author.login' /tmp/pr_meta.json)
PR_DESCRIPTION=$(jq -r '.body // "No description provided."' /tmp/pr_meta.json)
PR_DIFF=$(cat /tmp/pr_diff.txt)
FILE_LIST=$(jq -r '.files[].path' /tmp/pr_meta.json)

# Read the prompt template and substitute placeholders
PROMPT=$(cat "/skills/$SKILL_NAME/prompt.md")
PROMPT="${PROMPT//\{\{PR_NUMBER\}\}/$PR_NUMBER}"
PROMPT="${PROMPT//\{\{PR_TITLE\}\}/$PR_TITLE}"
PROMPT="${PROMPT//\{\{PR_AUTHOR\}\}/$PR_AUTHOR}"
PROMPT="${PROMPT//\{\{PR_DESCRIPTION\}\}/$PR_DESCRIPTION}"
PROMPT="${PROMPT//\{\{FILE_LIST\}\}/$FILE_LIST}"
PROMPT="${PROMPT//\{\{PR_DIFF\}\}/$PR_DIFF}"

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
claude -p "$PROMPT" \
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
