---
name: start
description: |
  Challenge-me hub — single entry point to pick a challenge mode for your PR.
  Use when the user asks to "challenge me", "challenge-me", "challenge-me:start", or wants to pick a challenge mode.
  This is the default entry point for the challenge-me plugin.
allowed-tools: AskUserQuestion, Bash, Read, Write, Edit, Grep, Glob, Agent
model: opus
---

# Challenge Me — Start

You are the entry point for the challenge-me plugin. Your job is to detect the PR, display a welcome header, and let the user pick which challenge mode they want.

## Phase 1: PR Detection

The user may provide a PR number or URL as an argument (e.g. `/challenge-me:start #42` or `/challenge-me:start 42`). If provided, use it: `gh pr view <number> --json ...`. Otherwise, detect the PR from the current branch.

Run `gh pr view [<number>] --json number,title,body,baseRefName,headRefName,additions,deletions,changedFiles,url,state,isDraft` to get the current PR metadata.

**If no PR exists**: inform the user ("No open PR found. Create one with `gh pr create` or specify a PR number: `/challenge-me:start #42`.") and stop.
**If the PR is merged or closed**: inform the user and stop.

## Phase 2: Welcome Header

Display:

```
## Challenge Me

**PR:** #[number] — [title]
**PR URL:** [url]
**Files changed:** [changedFiles] | **Lines:** +[additions] / -[deletions]

---
```

## Phase 3: Mode Selection

Use `AskUserQuestion` to ask:
- Question: "What would you like to do?"
- Options:
  - "Socratic Quiz — open-ended questions to test your understanding"
  - "MCQ — multiple-choice questions with instant feedback"
  - "Review — static analysis of complexity, design, and potential errors"
  - "Is it obvious? — find code that needs comments or documentation"
  - "Learn — deepen your understanding of the concepts in this PR"
  - "Explore — get quizzed on any part of the codebase (no PR needed)"
  - "My Progress — view your areas to revisit and growth over time"

## Phase 4: Redirect

Based on the user's selection, use the **Skill tool** to invoke the corresponding skill. Pass the PR number as an argument so it doesn't need to re-detect it.

Map:
- "Socratic Quiz" → invoke skill `challenge-me:run` with arg `#[number]`
- "MCQ" → invoke skill `challenge-me:mcq` with arg `#[number]`
- "Review" → invoke skill `challenge-me:review` with arg `#[number]`
- "Is it obvious?" → invoke skill `challenge-me:hint` with arg `#[number]`
- "Learn" → invoke skill `challenge-me:learn` with arg `#[number]`
- "Explore" → invoke skill `challenge-me:explore` (no PR number needed — the skill will ask for a target)
- "My Progress" → invoke skill `challenge-me:progress`

**Do NOT execute the skill's workflow yourself.** Just redirect. Each skill handles its own full lifecycle (progress tracking, questions, scoring, saving).

## Language

Default to English. If the user responds in another language, switch all output to match.
