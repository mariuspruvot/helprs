---
deferred_work_file: '{implementation_artifacts}/deferred-work.md'
---

# Step 4: Present and Act

## RULES

- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`
- When `{spec_file}` is set, always write findings to the story file before offering action choices.
- `decision-needed` findings must be resolved before handling `patch` findings.

## INSTRUCTIONS

### 1. Clean review shortcut

If zero findings remain after triage (all dismissed or none raised): state that and proceed to section 6 (Sprint Status Update).

### 2. Write findings to the story file

If `{spec_file}` exists and contains a Tasks/Subtasks section, append a `### Review Findings` subsection. Write all findings in this order:

1. **`decision-needed`** findings (unchecked):
   `- [ ] [Review][Decision] <Title> — <Detail>`

2. **`patch`** findings (unchecked):
   `- [ ] [Review][Patch] <Title> [<file>:<line>]`

3. **`defer`** findings (checked off, marked deferred):
   `- [x] [Review][Defer] <Title> [<file>:<line>] — deferred, pre-existing`

Also append each `defer` finding to `{deferred_work_file}` under a heading `## Deferred from: code review ({date})`. If `{spec_file}` is set, include its basename in the heading (e.g., `code review of story-3.3 (2026-03-18)`). One bullet per finding with description.

### 3. Present summary

Announce what was written:

> **Code review complete.** <D> `decision-needed`, <P> `patch`, <W> `defer`, <R> dismissed as noise.

If `{spec_file}` is set, add: `Findings written to the review findings section in {spec_file}.`
Otherwise add: `Findings are listed above. No story file was provided, so nothing was persisted.`

### 4. Resolve decision-needed findings

If `decision_needed` findings exist, present each one with its detail and the options available. The user must decide — the correct fix is ambiguous without their input. Walk through each finding (or batch related ones) and get the user's call. Once resolved, each becomes a `patch`, `defer`, or is dismissed.

If the user chooses to defer, ask: Quick one-line reason for deferring this item? (helps future reviews): — then append that reason to both the story file bullet and the `{deferred_work_file}` entry.

**HALT** — I am waiting for your numbered choice. Reply with only the number (or "0" for batch). Do not proceed until you select an option.

### 5. Handle `patch` findings

If `patch` findings exist (including any resolved from step 4), HALT. Ask the user:

If `{spec_file}` is set, present all three options (if >3 `patch` findings exist, also show option 0):

> **How would you like to handle the <Z> `patch` findings?**
> 0. **Batch-apply all** — automatically fix every non-controversial patch (recommended when there are many)
> 1. **Fix them automatically** — I will apply fixes now
> 2. **Leave as action items** — they are already in the story file
> 3. **Walk through each** — let me show details before deciding

If `{spec_file}` is **not** set, present only options 1 and 3 (omit option 2 — findings were not written to a file). If >3 `patch` findings exist, also show option 0:

> **How would you like to handle the <Z> `patch` findings?**
> 0. **Batch-apply all** — automatically fix every non-controversial patch (recommended when there are many)
> 1. **Fix them automatically** — I will apply fixes now
> 2. **Walk through each** — let me show details before deciding

**HALT** — I am waiting for your numbered choice. Reply with only the number (or "0" for batch). Do not proceed until you select an option.

- **Option 0** (only when >3 findings): Apply all non-controversial patches without per-finding confirmation. Skip any finding that requires judgment. Present a summary of changes made and any skipped findings.
- **Option 1**: Apply each fix. After all patches are applied, present a summary of changes made. If `{spec_file}` is set, check off the items in the story file.
- **Option 2** (only when `{spec_file}` is set): Done — findings are already written to the story.
- **Walk through each**: Present each finding with full detail, diff context, and suggested fix. After walkthrough, re-offer the applicable options above.

  **HALT** — I am waiting for your numbered choice. Reply with only the number (or "0" for batch). Do not proceed until you select an option.

**✅ Code review actions complete**

- Decision-needed resolved: <D>
- Patches handled: <P>
- Deferred: <W>
- Dismissed: <R>

### 6. Update story status and sync sprint tracking

Skip this section if `{spec_file}` is not set.

#### Determine new status based on review outcome

- If all `decision-needed` and `patch` findings were resolved (fixed or dismissed) AND no unresolved HIGH/MEDIUM issues remain: set `{new_status}` = `awaiting-manual-qa`. Update the story file Status section to `awaiting-manual-qa`.
- If `patch` findings were left as action items, or unresolved issues remain: set `{new_status}` = `in-progress`. Update the story file Status section to `in-progress`.

**IMPORTANT — handoff contract (epic-2 retro action #2, 2026-04-10):** The `done` status is NEVER set by this workflow. Only the Project Lead can transition a story from `awaiting-manual-qa` → `done` after signing the Manual QA Checklist in the story file. This is the explicit handoff contract. Any code path that would set `done` here is a bug.

Save the story file.

#### Sync sprint-status.yaml

If `{story_key}` is not set, skip this subsection and note that sprint status was not synced because no story key was available.

If `{sprint_status}` file exists:

1. Load the FULL `{sprint_status}` file.
2. Find the `development_status` entry matching `{story_key}`.
3. If found: update `development_status[{story_key}]` to `{new_status}`. Update `last_updated` to current date. Save the file, preserving ALL comments and structure including STATUS DEFINITIONS.
4. If `{story_key}` not found in sprint status: warn the user that the story file was updated but sprint-status sync failed.

If `{sprint_status}` file does not exist, note that story status was updated in the story file only.

#### Completion summary

Branch on `{new_status}`:

**CASE A — `{new_status}` = `awaiting-manual-qa`** (clean review, ready for Project Lead):

> **🟡 Code review automated phase complete — Manual QA required**
>
> **Story:** `{story_key}`
> **Status:** `awaiting-manual-qa` (was `review`)
> **Issues Fixed:** <fixed_count>
> **Action Items Created:** <action_count>
> **Deferred:** <W>
> **Dismissed:** <R>
>
> ---
>
> **@{user_name}** — this story is now waiting on your manual validation.
> Automated tests + code review are done. Nothing will progress until you
> sign off the Manual QA Checklist.
>
> **What to do next:**
> 1. Open the story file: `{spec_file}`
> 2. Jump to the `## Manual QA Checklist` section
> 3. Bring up the stack:
>    ```
>    docker compose up --build
>    ```
> 4. Walk the checklist, tick each box, sign with date + initials at the bottom
> 5. When all items pass: transition the story Status to `done` in the story
>    file AND in `{sprint_status}` — you can ask an agent to do this step, but
>    only AFTER you have personally signed the checklist.
>
> **If blocked:** leave an unchecked item with a note explaining what failed.
> The Dev agent will pick it back up via `dev-story` on this same story key.

**CASE B — `{new_status}` = `in-progress`** (unresolved issues, back to dev):

> **🔴 Code review complete — action items remain**
>
> **Story:** `{story_key}`
> **Status:** `in-progress` (was `review`)
> **Issues Fixed:** <fixed_count>
> **Action Items Created:** <action_count>
> **Deferred:** <W>
> **Dismissed:** <R>
>
> Unresolved `patch` findings or HIGH/MEDIUM issues remain. The story
> is NOT ready for Manual QA — it returns to the Dev agent to address
> the outstanding items before another code-review pass.

### 7. HALT — handoff is terminal

> **⛔ This workflow stops here.**
>
> Do NOT auto-proceed to `dev-story`, `create-story`, or any other workflow.
>
> - If the story is in `awaiting-manual-qa`: the Project Lead must sign off
>   the Manual QA Checklist before any downstream action.
> - If the story is in `in-progress`: the user decides when to re-invoke
>   `dev-story` to address the remaining action items.
>
> If you are an agent reading this: your job is done. Exit cleanly. Offering
> a "next story" option here would re-create the exact silent-skip that epic-2
> retro action items #1-3 were written to fix.

**HALT** — end of code-review workflow. No numbered options, no follow-up actions. The next action belongs to the human.
