# Skill Specification

All helPRs skills must follow this specification. Skills run inside ephemeral Docker containers with Claude Code CLI -- they must be fully self-contained and executable with zero prior context.

## Required files

Every skill directory must contain exactly three files:

### `CLAUDE.md`

The entry point Claude Code reads when it enters the skill directory. This file must contain:

- **Purpose**: A clear one-paragraph description of what the skill does.
- **Workflow**: Step-by-step instructions for Claude Code to follow. Claude Code has no memory between runs -- every instruction must be explicit.
- **Output format**: Exactly how output should be structured so the frontend can parse it.
- **Constraints**: What the skill must NOT do (e.g., modify files, push commits).

Guidelines for writing `CLAUDE.md`:
- Write in the imperative ("Read the diff", "Generate questions"), not descriptive ("This skill reads the diff").
- Be explicit about tool usage -- specify when to use `Read`, `Grep`, `Glob`, `Bash`, etc.
- Include the complete output format with examples. The frontend parses this output.
- Assume Claude Code has never seen this repository before.

### `prompt.md`

The main prompt template. The container orchestrator fills placeholders before passing this to Claude Code as the initial prompt.

**Required placeholders** (filled by the orchestrator):

| Placeholder | Source |
|-------------|--------|
| `{{PR_DIFF}}` | Full unified diff |
| `{{PR_TITLE}}` | Pull request title |
| `{{PR_DESCRIPTION}}` | Pull request body |
| `{{FILE_LIST}}` | Newline-separated list of changed files |
| `{{PR_NUMBER}}` | Pull request number |
| `{{PR_AUTHOR}}` | GitHub username of the PR author |

Skills may use any subset of these placeholders. Unused placeholders are not injected.

Guidelines for `prompt.md`:
- Start with a brief context block so Claude Code understands the situation.
- Reference `CLAUDE.md` for the detailed workflow -- do not duplicate instructions.
- Keep the prompt focused on the specific PR being analyzed.

### `config.yaml`

Skill metadata and configuration. Required fields:

```yaml
name: skill-name                    # kebab-case, must match folder name
description: "One-line description" # Shown in skill selection UI
version: "1.0.0"                    # SemVer
fetch_strategy: shallow_clone       # How the repo is fetched into the container
estimated_duration: "5-10 min"      # Human-readable time estimate
output_format: sse_stream           # How output is delivered to the frontend
```

**Field definitions:**

| Field | Required | Values | Description |
|-------|----------|--------|-------------|
| `name` | yes | kebab-case string | Must match the folder name |
| `description` | yes | string | One-line description for UI display |
| `version` | yes | SemVer string | Skill version |
| `fetch_strategy` | yes | `shallow_clone`, `diff_only`, `none` | How much of the repo the container needs |
| `estimated_duration` | yes | string | Time estimate shown to the user |
| `output_format` | yes | `sse_stream`, `json`, `markdown` | How results are delivered |
| `model` | no | string | Claude model preference (default: decided by orchestrator) |
| `max_turns` | no | integer | Maximum conversation turns (default: unlimited) |
| `tools` | no | list of strings | Claude Code tools the skill needs (default: all) |
| `tags` | no | list of strings | Categorization tags for filtering |

**`fetch_strategy` options:**
- `shallow_clone` -- Full repo at depth 1. Use when the skill needs file context beyond the diff.
- `diff_only` -- Only the diff is provided (no repo checkout). Use for lightweight analysis.
- `none` -- No repo access. Use for skills that only process metadata.

**`output_format` options:**
- `sse_stream` -- Output is streamed token-by-token via Server-Sent Events. Default for interactive skills.
- `json` -- Output is a single JSON blob returned when the skill completes. Use for machine-readable results.
- `markdown` -- Output is a single markdown document returned when the skill completes.

## Optional files

Skills may include additional files for context or examples:

| File | Purpose |
|------|---------|
| `examples/` | Example inputs/outputs for testing |
| `scoring.md` | Detailed scoring rubric (referenced from `CLAUDE.md`) |
| `context.md` | Additional domain context the skill needs |

Optional files must be explicitly referenced from `CLAUDE.md` -- Claude Code will not discover them automatically.

## Naming conventions

- Skill folder: `kebab-case` (e.g., `challenge-me`, `review-security`, `explain-changes`)
- Files: exact names as specified above -- no variations
- Placeholders in `prompt.md`: `{{UPPER_SNAKE_CASE}}` with double curly braces

## Output streaming

All interactive skills should use `sse_stream` output format. The frontend expects output as a continuous stream of text that it renders incrementally.

For structured results (scores, verdicts), emit them as markdown within the stream. The frontend parses known patterns:

- `### Score: X / 10` -- extracted as the session score
- `### Verdict` -- extracted as the summary verdict
- Fenced code blocks with `yaml` or `json` language tags -- parsed as structured data if needed

Skills must NOT emit raw JSON interspersed with markdown. Either the entire output is JSON (`output_format: json`) or the entire output is streamed markdown/text (`output_format: sse_stream`).

## Constraints

All skills run in read-only mode against the repository:
- Skills must NOT modify repository files, create commits, or push changes.
- Skills must NOT access secrets, tokens, or credentials beyond what the orchestrator provides.
- Skills must NOT make network requests outside the container (no calling external APIs).
- Skills must NOT persist state between runs -- every invocation starts fresh.
