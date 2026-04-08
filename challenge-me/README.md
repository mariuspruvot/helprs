# challenge-me

Challenge yourself on your PRs and your codebase — verify you truly understand the code you write and maintain. Keep learning as part of the dev process, even when AI does the heavy lifting.

## Quick Start

```
/challenge-me:start
```

Single entry point — picks up your current branch's PR and lets you choose a mode. You can also target a specific PR:

```
/challenge-me:start #42
```

## Skills

| Skill | Command | Description |
|-------|---------|-------------|
| **start** | `/challenge-me:start` | Hub — pick a challenge mode from a menu |
| **run** | `/challenge-me:run` | Socratic quiz — open-ended questions, interactive or quiz mode, score /10 |
| **mcq** | `/challenge-me:mcq` | Multiple-choice quiz — structured questions with selectable options |
| **review** | `/challenge-me:review` | Static PR analysis — complexity, design issues, potential errors |
| **hint** | `/challenge-me:hint` | "Is it obvious?" — find code that needs comments or documentation |
| **learn** | `/challenge-me:learn` | Deepening session — explore the concepts and patterns behind your PR |
| **explore** | `/challenge-me:explore` | Codebase challenge — get quizzed on any file, directory, or concept (no PR needed) |
| **progress** | `/challenge-me:progress` | View your areas to revisit, strengths, and growth over time |

## Recommended Workflow

```
                    /challenge-me:start
                           |
              +------------+------------+
              |            |            |
           review        run/mcq      hint
        (find issues)  (test yourself) (docs)
              |            |
              +-----+------+
                    |
                  learn
            (deepen knowledge)
                    |
                progress
            (track your growth)
```

1. **review** first — see what a senior reviewer would flag
2. **run** or **mcq** — test your understanding of your own changes
3. **hint** — make sure non-obvious code is documented
4. **learn** — go deeper on concepts you struggled with
5. **explore** — challenge yourself on code you didn't write or are onboarding onto
6. **progress** — see your areas to revisit and growth over time

## Progress Tracking

On your first interactive session (`run`, `mcq`, `learn`, or `explore`), you'll be asked:

> "Would you like to enable progress tracking?"

If you say yes, a `.challenge-me/` directory is created in your repo (automatically gitignored). It stores:

- **Areas to revisit** — topics where you can deepen your understanding
- **Strengths** — topics where you've shown solid grasp
- **Growth** — topics that moved from "to revisit" to "strength" over time

Future sessions use this data to **focus questions on your areas to revisit** — creating a feedback loop that helps you grow.

View your progress anytime with `/challenge-me:progress`.

## Explore mode (no PR needed)

Challenge yourself on any part of the codebase:

```
/challenge-me:explore src/payments/
/challenge-me:explore "the authentication system"
/challenge-me:explore RetryPolicy
```

Accepts a file path, directory, class name, or concept. Great for onboarding or deepening knowledge of code you didn't write.

## All PR-based skills accept a PR number

Every skill accepts an optional PR number or URL argument:

```
/challenge-me:run #42
/challenge-me:review 42
/challenge-me:hint #42
```

If omitted, the PR is detected from the current branch.

## Session Format

All skills follow a consistent format:

1. **Header** — `## Challenge Me — [Mode]` + PR metadata (number, title, URL, files, lines)
2. **Session** — Questions, analysis, or learning content
3. **Results** — Score with visual bar (where applicable), strengths, areas to improve, verdict
4. **Save** — Option to save session to progress tracker (interactive skills)

## Requirements

- `gh` CLI installed and authenticated
- An open PR for PR-based skills (on current branch, or specified by number)
- `explore` and `progress` work without a PR
