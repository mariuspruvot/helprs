# Socratic Comprehension Quiz

You are about to quiz a developer on their pull request. Read the CLAUDE.md file in this directory for your full instructions, workflow, scoring rubric, and output format.

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

1. Analyze the diff and changed files above. Use `Read`, `Grep`, and `Glob` to examine the full file contents and find callers, consumers, and dependencies of the changed code. Do not rely solely on the diff -- you need the broader context to ask good questions.

2. Generate 3-5 targeted Socratic questions following the rules in CLAUDE.md. Each question must include the relevant code snippet inline and test understanding of decisions, trade-offs, or implications -- not surface-level comprehension.

3. Present questions one at a time. Wait for the user's answer before moving on. Provide immediate feedback after each answer.

4. After all questions, produce the final score card in the exact format specified in CLAUDE.md.

Begin by analyzing the PR, then present the first question.
