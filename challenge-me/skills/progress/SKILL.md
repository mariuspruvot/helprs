---
name: progress
description: |
  View your challenge-me progress — areas to revisit, strengths, and growth over time.
  Use when the user asks to "show my progress", "challenge-me progress", "what should I review", "my weak areas", "how am I doing", or wants to see their challenge-me history.
allowed-tools: AskUserQuestion, Bash, Read, Write, Grep, Glob
model: sonnet
---

# Challenge Me — Progress

You read the user's saved challenge-me sessions and present a clear, encouraging summary of their learning journey.

## Phase 1: Check Tracking Data

Check if `.challenge-me/sessions/` exists and contains YAML files.

**If the directory does not exist or is empty:** inform the user:
> "No progress data yet. Run a challenge session (`/challenge-me:run`, `/challenge-me:mcq`, or `/challenge-me:learn`) and save your results to start tracking."

And stop.

## Phase 2: Read All Sessions

Read all `.yaml` files in `.challenge-me/sessions/`. Parse each file to extract:
- `date`, `skill`, `pr.number`, `pr.title`
- `areas_to_revisit` (list of `{topic, detail, files}`)
- `strengths` (list of `{topic, detail}`)
- `score` (if present — run/mcq)
- `topics_explored` and `understanding` (if present — learn)

## Phase 3: Aggregate & Analyze

### Areas to Revisit (sorted by frequency)

Count how many times each `topic` appears across all sessions' `areas_to_revisit`. Sort by frequency (most recurring first). For each topic, list the most recent detail/context.

### Strengths

Count how many times each `topic` appears across all sessions' `strengths`. These are the user's confirmed strong areas.

### Progression

If there are multiple sessions over time:
- Note if a topic that was in `areas_to_revisit` in an earlier session moved to `strengths` in a later one — this is **growth**, highlight it.
- Note if a topic keeps appearing in `areas_to_revisit` across 3+ sessions — this is a **recurring area to deepen**, suggest using `/challenge-me:learn` focused on it.

## Phase 4: Output

Present in this format:

```
## Challenge Me — Your Progress

**Sessions:** [N] | **Since:** [earliest date] | **Latest:** [most recent date]
**Skills used:** [list of distinct skills used, e.g. "run (3), mcq (2), learn (1)"]

---

### Areas to Deepen

Topics that came up across your sessions — focus your next learning here.

| Topic | Times | Latest context |
|-------|-------|----------------|
| [topic] | [N] | [most recent detail] |
| ... | ... | ... |

### Your Strengths

Topics where you've consistently demonstrated solid understanding.

| Topic | Times confirmed |
|-------|----------------|
| [topic] | [N] |
| ... | ... |

### Growth

[If any topic moved from "areas to revisit" to "strengths" across sessions, highlight it here:]
- **[topic]** — first flagged on [date], confirmed as strength on [date]. Nice progress.

[If no growth detected yet, write: "Keep going — growth shows up after a few sessions."]

### Suggested Next Steps

Based on your progress:
- [If recurring areas exist:] `/challenge-me:learn` — focus on **[top recurring topic]** to deepen your understanding
- [If recent session had low score:] `/challenge-me:run` — re-challenge yourself on PR #[number]
- [If no recent sessions:] Pick a recent PR and run `/challenge-me:start`

---
*Progress tracking is local and gitignored. Your data stays on your machine.*
```

## Phase 5: Housekeeping

After displaying the progress summary, check the number of session files in `.challenge-me/sessions/`.

**If there are 15 or more sessions**, use `AskUserQuestion` to ask:
- Question: "You have [N] saved sessions. Want to clean up old data?"
- Options:
  - "Keep all — I like having the full history"
  - "Archive old — keep last 10, remove the rest"
  - "Reset — clear everything and start fresh"

Actions:
- **Keep all**: do nothing.
- **Archive old**: sort sessions by date, delete all except the 10 most recent. Confirm: "Cleaned up [X] old sessions. Kept the 10 most recent."
- **Reset**: delete all files in `.challenge-me/sessions/`. Confirm: "Progress reset. Your next session starts a clean slate."

**If there are fewer than 15 sessions**, skip this phase entirely.

## Important Notes

- **Positive framing always.** "Areas to deepen" not "weaknesses". "Growth" not "fixed mistakes". The goal is to encourage continued use.
- Do not display raw scores in the progress view — focus on topics and growth.
- If there's only 1 session, still show the output but note: "Just getting started — progress patterns emerge after a few sessions."
- Default to English. Switch language if user responds in another language.
