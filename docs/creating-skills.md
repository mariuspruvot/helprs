# Creating Skills

Skills are pluggable Claude Code agent definitions that run inside ephemeral Docker containers. Each skill is a self-contained folder mounted into the container at `/skills/<skill-name>/`.

This guide walks through creating a skill from scratch. For the formal specification, see [SKILL_SPEC.md](../skills/SKILL_SPEC.md).

---

## Anatomy of a Skill

Every skill directory contains exactly three files:

```
skills/
└── my-skill/
    ├── CLAUDE.md      # Workflow instructions for Claude Code
    ├── prompt.md      # Prompt template with PR placeholders
    └── config.yaml    # Metadata and configuration
```

---

## Step-by-Step: Creating a "Security Audit" Skill

### 1. Create the directory

```bash
mkdir skills/security-audit
```

### 2. Write `config.yaml`

This defines your skill's metadata and how it interacts with the system.

```yaml
name: security-audit
description: "Scan PR changes for common security vulnerabilities and misconfigurations"
version: "1.0.0"
fetch_strategy: diff_only
estimated_duration: "2-5 min"
output_format: sse_stream
tags:
  - security
  - vulnerabilities
  - owasp
```

**Field reference**:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Must match the folder name (kebab-case) |
| `description` | yes | Shown in the skill selection UI |
| `version` | yes | SemVer string |
| `fetch_strategy` | yes | How much repo context the container gets |
| `estimated_duration` | yes | Human-readable time estimate for the UI |
| `output_format` | yes | How results are delivered |
| `model` | no | Claude model preference |
| `max_turns` | no | Maximum conversation turns |
| `tools` | no | Restrict which Claude Code tools the skill can use |
| `tags` | no | Categorization for filtering |

**Fetch strategies**:
- `shallow_clone` -- full repo at depth 1 + PR checkout. Use when the skill needs file context beyond the diff (e.g., reading callers, imports, config files).
- `diff_only` -- only the diff is provided, no repo checkout. Fastest option for skills that analyze the diff alone.
- `none` -- no repo access. For skills that only process PR metadata.

### 3. Write `prompt.md`

The prompt template is filled with PR context by the container entrypoint before being passed to Claude Code as the initial prompt.

```markdown
# Security Audit

You are about to audit a pull request for security vulnerabilities.
Read the CLAUDE.md file in this directory for your full instructions.

## PR Context

**PR #{{PR_NUMBER}}**: {{PR_TITLE}}
**Author**: {{PR_AUTHOR}}

### Description

{{PR_DESCRIPTION}}

### Changed files

\`\`\`
{{FILE_LIST}}
\`\`\`

### Diff

\`\`\`diff
{{PR_DIFF}}
\`\`\`

## Instructions

Analyze the diff above for security vulnerabilities following the
workflow in CLAUDE.md. Focus on OWASP Top 10 categories relevant
to the changed code.
```

**Available placeholders**:

| Placeholder | Source |
|-------------|--------|
| `{{PR_NUMBER}}` | Pull request number |
| `{{PR_TITLE}}` | Pull request title |
| `{{PR_AUTHOR}}` | GitHub username of the PR author |
| `{{PR_DESCRIPTION}}` | Pull request body |
| `{{FILE_LIST}}` | Newline-separated list of changed files |
| `{{PR_DIFF}}` | Full unified diff |

Use any subset -- unused placeholders are not injected.

### 4. Write `CLAUDE.md`

This is the entry point Claude Code reads when it enters the skill directory. It must contain everything Claude Code needs to execute the skill with zero prior context.

```markdown
# Security Audit

You are a senior security engineer auditing a pull request for
vulnerabilities. Your goal is to identify real, exploitable issues
-- not style nits or theoretical concerns.

## Workflow

### Phase 1: Classify the changes

Read the diff provided in the initial prompt. Categorize each
changed file by risk level:
- **High risk**: auth, crypto, input handling, SQL, shell commands
- **Medium risk**: API endpoints, configuration, dependencies
- **Low risk**: tests, docs, styling

### Phase 2: Deep analysis

For high-risk files, use `Read` to examine the full file content.
Use `Grep` to find related code (e.g., other places the same
function is called, similar patterns).

Check for:
1. Injection (SQL, command, XSS, template)
2. Broken authentication / authorization
3. Sensitive data exposure (hardcoded secrets, logging PII)
4. Security misconfiguration
5. Insecure dependencies

### Phase 3: Report

For each finding, report:
- **Severity**: Critical / High / Medium / Low
- **Category**: OWASP category
- **Location**: File and relevant code snippet
- **Issue**: What's wrong
- **Fix**: How to fix it

If no issues found, say so explicitly.

## Output format

End with this summary block:

\`\`\`
---

## Results

**Files analyzed:** [N]

### Score: [X] / 10

### Findings

| # | Severity | Category | File | Issue |
|---|----------|----------|------|-------|
| 1 | High     | A03      | ... | ...   |

---
\`\`\`

## Constraints

- Do NOT modify any files in the repository.
- Focus on real, exploitable issues. Ignore style or best-practice
  suggestions that have no security impact.
- If the PR only changes tests or documentation, note "No
  security-relevant changes" and skip deep analysis.
```

**Guidelines for CLAUDE.md**:
- Write in the imperative: "Read the diff", "Check for injection" -- not "This skill reads the diff"
- Be explicit about tool usage: specify when to use `Read`, `Grep`, `Glob`, `Bash`
- Include the complete output format with examples -- the frontend parses this
- Assume Claude Code has never seen the repository before

### 5. Test locally

You can test your skill without the full helPRs stack by running Claude Code directly:

```bash
cd skills/security-audit

# Manually create a prompt with real PR data
cat prompt.md \
  | sed "s/{{PR_NUMBER}}/42/" \
  | sed "s/{{PR_TITLE}}/Add user input handling/" \
  | sed "s/{{PR_AUTHOR}}/octocat/" \
  | sed "s/{{PR_DESCRIPTION}}/Adds form validation/" \
  | sed "s/{{FILE_LIST}}/src\/handlers.py/" \
  | sed "s|{{PR_DIFF}}|$(gh pr diff 42 -R owner/repo)|" \
  > /tmp/test-prompt.md

# Run Claude Code with the skill's CLAUDE.md as context
cd /path/to/your/repo
claude -p "$(cat /tmp/test-prompt.md)" --output-format stream-json
```

Or test via the full helPRs stack:
1. Start helPRs locally: `docker compose up --build`
2. Build the runner: `make build-runner`
3. Open a PR on a connected repo
4. Select your skill from the UI

---

## Output Conventions

For `sse_stream` skills, the frontend parses known patterns from the streamed output:

- `### Score: X / 10` -- extracted as the session score
- `### Verdict` -- extracted as the summary verdict
- Fenced code blocks with `yaml` or `json` language tags -- parsed as structured data

Do not mix raw JSON with markdown. Either the entire output is JSON (`output_format: json`) or the entire output is streamed markdown/text (`output_format: sse_stream`).

---

## Constraints

All skills run in read-only mode:
- Must NOT modify repository files, create commits, or push changes
- Must NOT access secrets beyond what the orchestrator provides
- Must NOT make network requests outside the container
- Must NOT persist state between runs -- every invocation starts fresh
