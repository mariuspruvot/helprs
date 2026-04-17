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

# JSON-encode the prompt using node (available in the base image)
PROMPT_JSON=$(node -e "process.stdout.write(JSON.stringify(process.argv[1]))" "$PROMPT")

# Write the initial prompt as the first stream-json message to a FIFO.
FIFO=/tmp/claude-input
mkfifo "$FIFO"

# Keep a persistent write fd (fd 3) on the FIFO so that `cat` never sees EOF
# between individual docker-exec writes. Each `echo ... > $FIFO` from the
# orchestrator opens+writes+closes its own fd, but cat keeps reading because
# fd 3 is still open. The fd closes naturally when the container is stopped.
exec 3>"$FIFO"

# Send the initial prompt via the persistent handle
echo "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":${PROMPT_JSON}}}" >&3

# cat reads from FIFO until ALL writers close (fd 3 + any exec writers)
cat <"$FIFO" | exec claude \
    --input-format stream-json \
    --output-format stream-json \
    --verbose \
    --dangerously-skip-permissions \
    --max-turns 30
