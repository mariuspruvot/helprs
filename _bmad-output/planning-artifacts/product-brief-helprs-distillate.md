---
title: "Product Brief Distillate: helPRs"
type: llm-distillate
source: "product-brief-helprs.md"
created: "2026-04-08"
purpose: "Token-efficient context for downstream PRD creation"
---

# Product Brief Distillate: helPRs

## Core Concept

- helPRs = GitHub App creating Socratic LLM chat sessions per PR to challenge developer comprehension
- Comprehension-first, not defect-detection -- complements CodeRabbit/Copilot, does not compete
- Inspired directly by challenge-me Claude Code plugin (v1.4.0, papernest org) -- proven local prototype to web product pattern
- "Wave 4" of AI code review: Waves 1-3 are passive analysis, active remediation, one-click fixes. Wave 4 = comprehension-oriented
- Tagline candidates: "Understand your code before defending it", "Accountability infrastructure for the AI coding era", "The seatbelt for AI coding"

## challenge-me Plugin: Source Material for Prompts

- Plugin has 8 skills: run, mcq, review, hint, learn, explore, progress, start
- **run SKILL.md (~220 lines)** is the core Socratic prompt to port as helPRs system prompt -- must be read in full during PRD/architecture phases
- Scoring dimensions: Depth, Accuracy, Completeness, Insight (scale 0-10)
- Verdicts: Exceptional (9-10), Strong (7-8), Adequate (5-6), Weak (3-4), Insufficient (0-2)
- A score of 7-8 is the expected norm for someone who genuinely wrote and understands their PR
- 12 normalized topic categories: architecture, edge-cases, error-handling, blast-radius, security, performance, testing, maintainability, concurrency, data-modeling, api-design, observability
- Anti-cheat principles (reframed as "contextual depth"): never ask questions answerable by reading the diff alone; at least 30% require knowledge beyond the diff; frame around decisions/tradeoffs/consequences not descriptions; include questions about callers/consumers not in the diff
- Progress tracking uses `.challenge-me/sessions/` with YAML session results -- becomes server-side persistence in helPRs

## Rejected Ideas (do not re-propose)

- **MCQ / quiz mode for MVP** -- eliminated. Interactive Socratic chat is the stronger product identity. MCQ deferred to backlog
- **Batch mode (all questions at once)** -- eliminated. One question at a time with feedback is core UX
- **Separate LLM pre-processing step before question generation** -- eliminated. Too expensive in tokens. Analysis and question generation combined in single pass
- **Skills explore, hint, learn, review, progress** -- all eliminated from MVP. MVP = run mode only
- **Onboarding via historical PRs** -- eliminated from MVP. Deferred to expansion phase
- **Continuous training / manager dashboard** -- eliminated from MVP. Cultural risk of surveillance
- **Multi-LLM support** -- eliminated from MVP. Claude API only. Architect for multi-LLM from day one
- **Full self-hosted deployment** -- eliminated from MVP. Enterprise feature for later
- **Audit/compliance mode** -- requires anti-cheat which contradicts "cheating assumed" philosophy. Deferred
- **Admin dashboard in MVP** -- removed to reduce scope. Opinionated defaults (warm tone, scores private, feedback after each answer) ship instead. Dashboard comes in v1.1 when customization demand is proven
- **Manager-facing individual score visibility** -- explicitly rejected. Scores never surfaced to managers. Product builds understanding, not surveillance

## Requirements Hints

- **Dual challenge mechanic**: author AND reviewer both challenged on every PR. Different severity (author wrong = very serious, reviewer wrong = serious). Different question types (author = why/tradeoffs/edge cases, reviewer = what/impact/risks). This is the key product differentiator
- **Dynamic question count**: 3-5 (small <100 lines), 5-7 (medium 100-500), 7-10 (large >500)
- **Score visibility**: private by default (visible only to session participant). Team-level opt-in for shared visibility requires collective agreement, not admin toggle
- **GitHub status check**: informational only, NEVER merge-blocking. Hard product constraint, not configurable
- **Feedback model**: after each answer submission, show which questions revealed gaps, with explanations and links to relevant code sections. Feedback teaches, not just evaluates
- **Re-trigger**: new push to PR = option to re-run session with adapted questions based on what changed
- **Large PRs (2000+ lines)**: never refuse. Show informational message, select most critical files for detailed analysis, provide stats on all files. Nudge: "Smaller PRs = better reviews"
- **LLM hallucinations**: clear disclaimer ("AI-generated questions may contain inaccuracies") + report button. Report data feeds prompt improvement
- **Multi-language**: from day one. Questions and interface adapt to user language. Low effort with LLM
- **Cheating posture**: assumed and accepted. Stated clearly in positioning. Value is in the process of engaging with questions. Even using another LLM to help answer still involves reading the question, evaluating the response against codebase context
- **Bot suppression**: configurable -- suppress helPRs comments on PRs with specific labels (hotfix, urgent, trivial)
- **Authentication**: GitHub OAuth, seamless transition from PR comment to chat session. No login wall on unknown domain
- **Demo mode**: pre-loaded session on a famous open-source PR for zero-setup trial in under 60 seconds
- **Trial credits**: free initial sessions without BYOK requirement. BYOK becomes option after adoption, not prerequisite

## Technical Context

- **GitHub App architecture**: webhooks (pull_request.opened, pull_request.synchronize) as HTTP POST with HMAC SHA-256 verification. 25MB payload limit. API version 2026-03-10. No server-side clone -- everything via GitHub API (diff, files, tree, commits, PR body)
- **LLM**: Claude API only for MVP. BYOK (Bring Your Own Key) -- helPRs is pure orchestrator. Zero-retention policy from Anthropic API by default. No source code stored server-side
- **Context approach for MVP**: diff + immediate file context only. No RAG, no codebase indexing. Scale to RAG only if question quality demands it
- **System prompt**: inspired by challenge-me run SKILL.md, injected with diff + repo context. ~220 lines of proven prompt engineering
- **Design system**: OpenCode AI inspired -- Berkeley Mono font, warm dark theme (#201d1d background), flat/no-shadow, 4px radius, Apple HIG semantic colors. Terminal-like chat consistent with "everything is code" identity. Design tokens already documented in `/Users/marius.pruvot/perso/helprs/design/DESIGN.md`
- **Split view UX**: chat on left, diff/code on right. Author sees code being discussed without leaving helPRs
- **Session persistence**: server-side storage of session metadata only (score, topics, timestamps, question-response patterns). No source code retention
- **Socratic research foundations**: TreeInstruct (ACL 2024, state-space planning for adaptive question trees), Reflection-in-Reflection (2026, multi-agent Socratic dialogue), SoHF (Amazon Science, expert steering strategies)

## Competitive Intelligence

- **CodeRabbit**: $550M valuation, $88M raised, $15M revenue, 2M+ repos, 13M+ PRs, 180K reviews/month, $24/user/mo Pro, free for public repos. 4-platform support (GitHub, GitLab, Azure DevOps, Bitbucket). 40+ built-in linters
- **GitHub Copilot Code Review**: ~37-42% market share in broader AI coding. 60M+ total reviews, 4.7M paid subscribers, 90% Fortune 100 adoption, $19/user/mo bundled. March 2026 agentic architecture overhaul
- **Greptile**: $180M valuation (Benchmark-led), $30/dev/mo, no free tier. 82% bug catch rate. Full codebase indexing
- **Qodo (ex-CodiumAI)**: multi-agent architecture pioneer (Feb 2026), $30/user/mo Teams, 60.1% F1 score. Auto test generation
- **Sourcery**: $12/seat/mo, free for public repos. Cheapest paid tier
- **Market size**: AI code review ~$4B (2025) within $7.37B AI coding tools market. 26-45% CAGR. 1.3M+ repos use AI code review. 44% of developers have used one
- **Adjacent market**: developer assessment $2.71B (2026), projected $10.86B by 2035 at 16.5% CAGR. Broader talent assessment ~$30B
- **Key stat**: 41% of all new code is AI-generated. 73% daily AI tool usage in engineering teams. 96% of developers don't fully trust AI-generated code
- **No competitor addresses comprehension** -- all compete on defect detection axis. Category is unoccupied

## Business Model Details

- Per-seat pricing, ~$8-15/user/mo range (lower than market due to BYOK -- user provides own API keys)
- Free for public/open-source repos (acquisition funnel -- every session on public PR is free impression)
- Trial credits for first-time teams to remove BYOK barrier
- Enterprise tier: SSO, audit logs, custom question policies
- PLG motion: dev finds value on OSS -> installs on private repo -> manager sees reduced incidents -> enterprise contract
- BYOK unit economics: revenue is margin on orchestration, not inference. Infrastructure costs = webhook processing, session storage, web UI hosting. Need cost modeling during architecture phase
- Pricing to be refined via willingness-to-pay research (Van Westendorp or Gabor-Granger with 20+ potential buyers)

## Cultural and Adoption Risks (detailed)

- **Surveillance dynamic**: scores visible on PRs can feel like testing regardless of opt-in framing. Mitigated by private-by-default, never surfacing to managers, informational-only status check
- **Bot fatigue**: developers already dismiss automated PR comments (early AI review tools had 9:1 false positive ratio). helPRs must differentiate UX clearly
- **Reviewer challenge backlash**: quizzing reviewer on someone else's code could discourage reviews. Mitigated by framing as "review prep" and warm default tone
- **"Anti-cheat" language**: adversarial framing contradicts empowerment positioning. Reframed as "contextual depth" in all user-facing materials
- **Mandatory usage risk**: if a manager mandates helPRs, it contradicts opt-in philosophy and becomes culturally radioactive. Product philosophy must be stated clearly: recommended, never required
- **Performance review misuse**: comprehension scores used in reviews could create legal/HR liability for customers. Explicitly not designed for this. No manager-facing score dashboards

## Open Questions

- Exact pricing point within $8-15 range -- needs willingness-to-pay research
- How to generate "beyond the diff" questions without codebase indexing in MVP -- inferred from diff context or requires minimal GitHub API calls for related files?
- Admin dashboard timing -- v1.1 or later? What's the minimum configuration surface teams actually need?
- Long-term vision refinement -- onboarding tool? Developer assessment platform? Compliance artifact generator? TBD based on market signals
- Anthropic partnership potential -- featured case study, API credits for early adopters, co-development of comprehension-specific model behaviors?
- Integration strategy with CodeRabbit/Qodo -- "Better Together" co-marketing feasibility?

## PMF Signals to Track

- \>30% of PRs trigger a started session
- \>60% session completion rate
- \>40% return usage on consecutive PRs
- Average score at session 10 >= 15% higher than session 1 (across 50+ dev cohorts, within 6 months)
- NPS > 30 from developers
- Cross-pollination: developers who use helPRs on one project request it on other projects

## Phased Roadmap (from brainstorming/research)

- **Phase 1 -- MVP (weeks 1-6)**: GitHub App + Claude API + Socratic prompts + web chat + trial credits + demo mode
- **Phase 2 -- Refinement (months 2-4)**: adaptive difficulty (TreeInstruct-inspired), multi-dimension questions (architecture, testing, security, design), session analytics, admin dashboard
- **Phase 3 -- Scale (months 4-8)**: multi-agent question generation, optional codebase context via lightweight RAG, gamification (streaks, leaderboards, badges), enterprise features (SSO, audit logs)
