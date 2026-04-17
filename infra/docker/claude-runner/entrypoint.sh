#!/bin/bash
set -euo pipefail

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

# Write the initial prompt as the first stream-json message to a FIFO.
# The API will write subsequent user messages to the container's stdin.
FIFO=/tmp/claude-input
mkfifo "$FIFO"

# Feed the initial prompt, then keep the FIFO open for subsequent messages
# from the container orchestrator (written via docker attach/exec).
{
  echo "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":$(echo "$PROMPT" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}}"
  # Keep stdin open -- the orchestrator sends follow-up messages here
  cat "$FIFO"
} | exec claude \
    --input-format stream-json \
    --output-format stream-json \
    --verbose \
    --dangerously-skip-permissions \
    --max-turns 30
