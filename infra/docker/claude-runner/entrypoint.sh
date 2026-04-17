#!/bin/bash
set -euo pipefail

# Authenticate with GitHub using the injected token
echo "$GITHUB_TOKEN" | gh auth login --with-token

# Clone the repo (shallow) and check out the PR branch
gh repo clone "$REPO_FULL_NAME" /workspace -- --depth=1
cd /workspace
gh pr checkout "$PR_NUMBER"

# Run the skill via Claude Code CLI
exec claude --skill "$SKILL_NAME" -p "$(cat /skills/$SKILL_NAME/prompt.md)"
