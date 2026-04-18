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

# gh CLI auto-detects GITHUB_TOKEN env var -- no explicit login needed.
gh auth status > /dev/null 2>&1 || {
  echo "ERROR: GitHub authentication failed" >&2
  exit 1
}

# Clone the repo and check out the PR branch
gh repo clone "$REPO_FULL_NAME" /workspace
cd /workspace
gh pr checkout "$PR_NUMBER"

# Fetch PR metadata for the prompt context
PR_TITLE=$(gh pr view "$PR_NUMBER" --json title --jq '.title')
PR_AUTHOR=$(gh pr view "$PR_NUMBER" --json author --jq '.author.login')
PR_DESCRIPTION=$(gh pr view "$PR_NUMBER" --json body --jq '.body // "No description provided."')
PR_DIFF=$(gh pr diff "$PR_NUMBER")
FILE_LIST=$(gh pr view "$PR_NUMBER" --json files --jq '.files[].path')

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
