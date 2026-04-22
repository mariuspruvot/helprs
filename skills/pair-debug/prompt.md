# Pair Debug -- Find the Injected Bug

You are about to simulate a pair debugging session. Read the CLAUDE.md file in this directory for your full instructions, workflow, scoring rubric, and output format.

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

1. Analyze the diff and changed files above. Use `Read`, `Grep`, and `Glob` to understand the full context.
2. Identify a section where a subtle, realistic bug could be injected.
3. Present the buggy code and challenge the developer to find the bug.
4. Act as a helpful debugging partner -- answer questions truthfully.
5. After the developer submits their diagnosis, reveal the bug and score.
6. Produce the score card in the exact format specified in CLAUDE.md.

Begin by analyzing the PR, then present the buggy code.
