#!/bin/bash
set -euo pipefail

# Authenticate with GitHub using the injected token
echo "$GITHUB_TOKEN" | gh auth login --with-token

# Clone the repo (shallow) and check out the PR branch
gh repo clone "$REPO_FULL_NAME" /workspace -- --depth=1
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

# Run Claude Code in non-interactive print mode
# --dangerously-skip-permissions: no human to approve tool use in a container
# --print: non-interactive, streams output to stdout
# -p is implicit when prompt is provided after --print
exec claude \
    --print \
    --dangerously-skip-permissions \
    --model sonnet \
    --output-format stream-json \
    "$PROMPT"
