# Test Me -- Predict Pass or Fail

You are about to test whether a developer can predict the behavior of their own code. Read the CLAUDE.md file in this directory for your full instructions, workflow, scoring rubric, and output format.

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

1. Analyze the diff and changed files above. Use `Read`, `Grep`, and `Glob` to understand the full context and existing tests.
2. Write 4-5 test cases (mix of pass and fail) targeting the changed code.
3. Present tests one at a time. Ask: "Will this test pass or fail? Why?"
4. Reveal the result after each prediction. Evaluate the reasoning.
5. After all tests, produce the score card in the exact format specified in CLAUDE.md.

Begin by analyzing the PR, then present the first test case.
