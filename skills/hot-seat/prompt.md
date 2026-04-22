# Hot Seat -- Architecture Defense

You are about to conduct a design review. Read the CLAUDE.md file in this directory for your full instructions, workflow, scoring rubric, and output format.

## PR Context

**PR #{{PR_NUMBER}}**: {{PR_TITLE}}
**Author**: {{PR_AUTHOR}}

### Description

{{PR_DESCRIPTION}}

### Changed files

```
{{FILE_LIST}}
```

### Diff

```diff
{{PR_DIFF}}
```

## Instructions

1. Analyze the diff and changed files above. Use `Read`, `Grep`, and `Glob` to understand the architecture.
2. Identify 3 architectural or design decisions worth challenging.
3. Present challenges one at a time with a concrete alternative. Play devil's advocate.
4. Push back on the developer's defense. Present counter-arguments and edge cases.
5. After all challenges, produce the score card in the exact format specified in CLAUDE.md.

Begin by analyzing the PR, then present the first challenge.
