# helPRs Skills

Skills are self-contained instruction packages that Claude Code executes inside ephemeral Docker containers. When a PR event triggers a skill, the orchestrator spins up an isolated container with Claude Code CLI, mounts the skill directory, and lets Claude Code run the workflow against the PR.

## What is a skill?

A skill is a folder containing everything Claude Code needs to perform a specific task on a pull request. Each skill is a "project" that Claude Code can discover and execute with zero prior context.

Skills are mounted read-only into the container at `/skills/<skill-name>/`. The container also gets a shallow clone of the repository at `/workspace/` and PR metadata injected as environment variables.

## Directory structure

```
skills/
  SKILL_SPEC.md          # Specification all skills must follow
  README.md              # This file
  challenge-me/          # A skill
    CLAUDE.md            # Instructions Claude Code reads on entry
    prompt.md            # Main prompt template with placeholders
    config.yaml          # Skill metadata and configuration
```

## Creating a new skill

1. Create a folder under `skills/` with a kebab-case name (e.g., `skills/my-skill/`).
2. Add the three required files: `CLAUDE.md`, `prompt.md`, `config.yaml`.
3. Follow the specification in `SKILL_SPEC.md` for required fields and conventions.
4. Test locally by pointing Claude Code at the skill directory.

## How skills are loaded into containers

The container orchestrator (API server) performs these steps:

1. Receives a webhook event (PR opened, comment trigger, etc.)
2. Resolves which skill to run based on the event and installation config
3. Starts an ephemeral Docker container with:
   - Claude Code CLI installed and authenticated
   - The skill directory mounted at `/skills/<name>/` (read-only)
   - A shallow clone of the repository at `/workspace/`
   - PR metadata injected via environment variables (`PR_NUMBER`, `PR_TITLE`, `PR_DESCRIPTION`, `PR_DIFF`, `FILE_LIST`)
4. Claude Code reads `CLAUDE.md` from the skill directory, which references `prompt.md`
5. The orchestrator fills placeholders in `prompt.md` and passes it as the initial prompt
6. Output is streamed back via SSE to the frontend

## Environment variables available in containers

| Variable | Description |
|----------|-------------|
| `PR_NUMBER` | Pull request number |
| `PR_TITLE` | Pull request title |
| `PR_DESCRIPTION` | Pull request body/description |
| `PR_DIFF` | Full unified diff of the PR |
| `FILE_LIST` | Newline-separated list of changed files |
| `REPO_OWNER` | Repository owner |
| `REPO_NAME` | Repository name |
| `PR_AUTHOR` | GitHub username of the PR author |
| `BASE_REF` | Base branch name |
| `HEAD_REF` | Head branch name |
