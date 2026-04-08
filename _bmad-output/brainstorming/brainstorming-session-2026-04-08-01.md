---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: []
session_topic: 'helPRs - GitHub App web product for PR review assistance via LLM chat sessions'
session_goals: 'Comprehensive product vision to produce a PRD - features, UX, architecture, positioning, monetization'
selected_approach: 'ai-recommended'
techniques_used: ['question-storming', 'scamper-method', 'chaos-engineering']
ideas_generated: [42]
context_file: ''
session_active: false
workflow_completed: true
---

# Brainstorming Session Results

**Facilitator:** Marius.pruvot
**Date:** 2026-04-08

## Session Overview

**Topic:** helPRs -- GitHub App / web product for PR review assistance. A GitHub App that creates a new LLM chat session for each new PR, challenging both the author's and reviewer's knowledge through dynamically-sized question sets. Inspired by the challenge-me Claude Code plugin and OpenCode AI design system.

**Goals:** Generate a comprehensive product vision covering features, UX, architecture, positioning, and monetization -- sufficient to write a complete PRD.

## Technique Selection

**Approach:** AI-Recommended Techniques

**Recommended Techniques:**

- **Question Storming (deep):** Map the full problem space before generating solutions -- surface blind spots in transitioning from local plugin to web product
- **SCAMPER Method (structured):** Systematically transform the existing challenge-me plugin into the helPRs web product
- **Chaos Engineering (wild):** Stress-test ideas against failure scenarios to identify constraints and edge cases for the PRD

## Technique Execution Results

### Phase 1: Question Storming

**Key questions surfaced:**

- Why would anyone pay for this, even 1 euro?
- Why can't a reviewer do a review alone?
- Is AI-generated code always understood by the person committing it?
- Who is the real buyer -- the dev or the company?
- Is this a training tool or a productivity tool?
- How does the LLM access code context without filesystem access?
- Does helPRs need the full repo or just the diff?
- How do companies ensure code is solid?
- Does the value lie in saving time or building confidence?
- Do leads/CTOs have a way to know if reviews are done seriously?
- Could helPRs create a surveillance/policing feeling?

**Breakthrough insight:** The explosion of AI-generated code (Copilot, Cursor) creates a new category of risk -- code that passes review without being understood by anyone. helPRs addresses this directly.

### Phase 2: SCAMPER Method

**Substitute:**
- GitHub API replaces filesystem access (GitHub App installed on repo)
- Web chat frontend replaces terminal CLI
- Target remains the author (not shifted to reviewer) -- "understand your code before defending it"

**Combine:**
- Run (socratic) mode only for MVP -- no MCQ
- Score combined with GitHub status check (visible on PR)
- Split view: chat + diff side by side in the frontend
- LLM analysis of diff used directly for question generation (no separate review pre-processing step -- too expensive in tokens)

**Adapt:**
- Progress tracking moves from local YAML to server-side persistence (basic: score, session, timestamps)
- Pre-prompt adapted from challenge-me SKILL.md (~220 lines) to system prompt injected with diff + repo context
- GitHub-native flow: PR opened -> app comments -> author clicks -> session -> score posted as status check
- Dynamic question count based on PR size: 3-5 (small), 5-7 (medium), 7-10 (large)

**Modify:**
- Scoring: visual, animated, configurable (public vs private via dashboard)
- Tone: senior staff engineer by default, configurable per team
- Feedback: delivered after submit (not real-time), configurable
- Re-triggerable: new push = option to re-run session with adapted questions

**Put to other uses:**
- Knowledge sharing: sessions shareable with the team
- Eliminated for MVP: onboarding, formation continue, audit/compliance

**Eliminate:**
- Skills explore, hint, learn, review, progress -- MVP = run only
- Quiz mode (all questions at once) -- interactive chat only
- Advanced progress tracking -- basic score history only
- Multi-LLM support -- Claude API only

**Reverse:**
- Both author AND reviewer are challenged (key differentiator)
- Different severity levels: author wrong = very serious, reviewer wrong = serious
- Different question types: author = deep (why, tradeoffs, edge cases), reviewer = comprehension (what, impact, risks)
- Score stays positive (comprehension), not negative (risk)
- No forced merge blocking -- empowerment, not policing

### Phase 3: Chaos Engineering

**Scenario: LLM-assisted cheating**
- Decision: assume and accept. Value is in the process, not the score. Stated clearly in positioning.
- Mitigation: highly contextual questions tied to repo-specific code make copy-paste to another LLM more effort than just thinking.

**Scenario: Oversized PRs (2000+ lines)**
- Decision: never refuse. Show informational message, select most critical files for detailed analysis, provide stats on all files.
- Bonus: "Smaller PRs = better reviews" nudge.

**Scenario: Sensitive code / private repos**
- Decision: BYOK (Bring Your Own Key). Enterprise uses their own Claude API key. helPRs is a pure orchestrator. No source code stored server-side. Code transits directly between client and Anthropic.

**Scenario: LLM hallucinations in questions**
- Decision: clear disclaimer ("AI-generated questions may contain inaccuracies") + report button. Report data used to improve prompts over time.

**Scenario: Non-English authors**
- Decision: multi-language from day one. Questions and interface adapt to user language.

## Idea Organization and Prioritization

### Theme 1: Positioning & Value Proposition

- **helPRs = comprehension tool, not a review tool.** "Understand your code before defending it."
- **Double challenge.** Author AND reviewer challenged at different severity levels.
- **Anti-LGTM.** Fights rubber-stamp approvals from both sides.
- **AI code angle.** Strong positioning for teams using Copilot/Cursor heavily -- "do you actually understand the code AI wrote for you?"
- **Cheating assumed.** Value is the process. Stated clearly. No policing.

### Theme 2: User Flow & GitHub Integration

- **Automatic trigger.** PR opened -> app posts comment with session link.
- **Re-trigger after push.** New commits = option to re-run. LLM adapts questions to what changed.
- **GitHub status check.** Score posted as check on PR. Configurable: public/private, author-only or author+reviewer.
- **Split view.** Chat on left, diff/code on right. Author sees the code being discussed without leaving helPRs.

### Theme 3: Quiz Experience

- **Socratic interactive.** One question at a time, answer, then feedback. No batch mode for MVP.
- **Dynamic question count.** Adapted to PR size: 3-5 (small <100 lines), 5-7 (medium 100-500), 7-10 (large >500).
- **Senior staff engineer tone.** Demanding but respectful. Configurable per team.
- **Feedback after submit.** Author answers, submits, receives feedback. No interruption of thought process. Configurable.
- **Multi-language.** Interface and questions adapt to user language.

### Theme 4: Architecture & Security

- **BYOK (Bring Your Own Key).** Enterprise uses own Claude API key. helPRs is a pure orchestrator.
- **No source code storage.** Only session metadata persists server-side (score, topics, timestamps).
- **GitHub App.** Installed on repo. Access to everything via GitHub API (diff, files, tree, commits, PR body). No server-side clone.
- **Pre-prompt.** System prompt inspired by challenge-me `run` skill (~220 lines), injected with diff and repo context.
- **Claude API only.** No multi-LLM for MVP.

### Theme 5: Dashboard & Configuration

- **Admin dashboard per org/repo.** Configurable settings:
  - Score visibility (public/private)
  - Challenge tone (demanding/encouraging)
  - Feedback timing (after submit/real-time)
  - Alert thresholds
- **Basic history.** Score per session, per author, per PR. No advanced progress tracking for MVP.
- **Knowledge sharing.** Option to share a session with the team.

### Theme 6: Design

- **OpenCode design system.** Monospace-first (Berkeley Mono), warm dark theme (#201d1d), flat/no-shadow, 4px radius, Apple HIG semantic colors.
- **Terminal-like chat.** Consistent with "everything is code" identity.

### Theme 7: Edge Cases & Constraints

- **Large PRs.** No refusal. Informational message + intelligent file selection. LLM receives stats for all files but detailed diff for critical files only.
- **LLM hallucinations.** Clear disclaimer + "report incorrect question" button. Data feeds prompt improvement.
- **Sensitive code.** Resolved by BYOK -- code transits between client and Anthropic, not through helPRs.

### Non-MVP Backlog

- MCQ / quiz mode
- Advanced progress tracking (recurring topics, growth, team dashboard)
- Continuous training / manager dashboard
- Onboarding via historical PRs
- Multi-LLM support
- Full self-hosted deployment
- Audit/compliance (requires anti-cheat)

## Key Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target user | Author AND reviewer | Both must prove comprehension, different severity |
| Challenge format | Socratic interactive (run) | Chat is interactive by nature, one question at a time |
| Question count | Dynamic (3-10 based on PR size) | Fixed count is unfair to small and large PRs |
| LLM cheating | Accept and assume | Value is in the process, not the score |
| Code security | BYOK | Enterprise uses own API key, helPRs never stores code |
| Score visibility | Configurable | Teams have different cultures, let them choose |
| Tone | Configurable (default: senior engineer) | Same reason -- culture varies |
| Large PRs | Intelligent selection, never refuse | Always provide value, even partial |
| Hallucinations | Disclaimer + report button | Honest about limits, collect data to improve |
| Language | Multi-language from day one | Global audience, low effort with LLM |
| Design system | OpenCode-inspired | Terminal-native, monospace-first, warm dark theme |

## Session Summary

**Techniques used:** Question Storming, SCAMPER, Chaos Engineering
**Duration:** ~45 minutes
**Ideas generated:** 42 organized ideas across 7 themes

**Breakthrough moments:**
1. The realization that AI-generated code creates a new category of review risk -- helPRs' strongest positioning angle
2. Both author AND reviewer should be challenged, but at different severity levels -- key product differentiator
3. BYOK architecture solves security concerns AND reduces helPRs operational costs simultaneously

**Next step:** Create a PRD from this brainstorming output using the `bmad-create-prd` skill.
