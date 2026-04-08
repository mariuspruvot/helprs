---
title: "Product Brief: helPRs"
status: "complete"
created: "2026-04-08"
updated: "2026-04-08"
inputs:
  - "_bmad-output/brainstorming/brainstorming-session-2026-04-08-01.md"
  - "_bmad-output/planning-artifacts/research/domain-ai-pr-review-github-apps-research-2026-04-08.md"
---

# Product Brief: helPRs

## Executive Summary

AI coding tools have created an unprecedented paradox: developers ship more code than ever, but understand less of what they ship. AI-assisted coding pushed PR volume up 29% year-over-year, while studies show AI-assisted developers score 17% lower on comprehension tests. The result is **comprehension debt** -- code that passes review without being understood by anyone.

Every AI code review tool on the market -- CodeRabbit ($550M valuation), GitHub Copilot (60M+ reviews), Greptile, Qodo -- competes on the same axis: find bugs, suggest fixes, generate tests. None asks the fundamental question: *does the person merging this code actually understand it?*

**helPRs is a GitHub App that challenges developers to prove they understand their own PRs.** For each pull request, helPRs creates a Socratic chat session powered by an LLM, asking targeted questions that probe comprehension -- not correctness. Both the PR author and reviewer are challenged, at different depth levels. The result is a comprehension score visible on the PR, turning the review from a rubber-stamp gate into a learning moment.

helPRs is not a replacement for code review tools -- it is accountability infrastructure for the AI coding era. The only AI code review tool that never touches your code. A team uses CodeRabbit to find bugs *and* helPRs to ensure they understand the code they're shipping.

## The Problem

76% of developers using AI tools report generating code they don't fully understand. AI coding agents produce code at 140-200 lines per minute; human comprehension operates at 20-40 lines per minute. This 5-7x gap creates a new class of risk: syntactically correct, well-formatted code that nobody on the team truly understands.

The review process is failing to catch this. Reviewers rubber-stamp with "LGTM" because AI-generated code *looks* clean -- the visual signals that historically triggered merge confidence are precisely the signals AI output excels at producing. 48% of AI-generated code contains potential security vulnerabilities, and AI-assisted code increases issue counts by 1.7x.

Engineering leaders have no visibility into this problem. DORA metrics track velocity, not understanding. There is no way to know whether a developer who merged 15 PRs this week understood any of them. When AI-written code fails in production, there is no mechanism to determine whether a human ever understood what shipped.

## The Solution

helPRs integrates as a GitHub App. When a PR is opened, helPRs posts a comment with a session link. The developer clicks through to a web-based chat interface (split view: chat on the left, diff/code on the right) where an LLM acting as a senior staff engineer asks Socratic questions about the changes.

**Key mechanics:**
- **Dynamic question count** adapted to PR size: 3-5 (small), 5-7 (medium), 7-10 (large)
- **Mutual comprehension**: author receives deep questions (why, tradeoffs, edge cases); reviewer receives comprehension questions (what, impact, risks). Both sides of the PR prove understanding -- transforming code review from a one-directional approval into a bilateral comprehension contract
- **Contextual depth**: questions deliberately go beyond the diff -- callers, consumers, architectural decisions, system-level impact. This surfaces blind spots that a self-review structurally cannot catch
- **Actionable feedback**: after submission, the developer sees which questions revealed gaps, with explanations and links to relevant code sections. The session teaches, not just evaluates
- **Comprehension score** posted as a GitHub status check (informational, never blocking). Score is private by default -- visible only to the session participant. Teams can opt into shared visibility collectively

The experience is opt-in and empowering, not policing. Value is in the process of thinking, not the score. Even if a developer uses another LLM to help answer, they still engage with the question, read the response, and evaluate it against their specific codebase context -- the act of engagement is the value.

## What Makes This Different

**Category creator, not competitor.** helPRs occupies an uncontested position -- "Wave 4" of AI code review. Every incumbent fights over defect detection accuracy. helPRs asks a question none of them answer: *do you understand what you're about to merge?*

**Complementary by design.** helPRs coexists with any review tool. CodeRabbit finds bugs; helPRs builds understanding. This avoids head-to-head competition with $550M-funded players and enables integration opportunities -- CodeRabbit's findings can feed into helPRs questions for deeper comprehension probing.

**Zero-trust security posture.** BYOK (Bring Your Own Key) architecture means enterprise teams use their own Claude API key. helPRs is a pure orchestrator -- no source code is stored, indexed, or retained server-side. Code transits directly between the client and Anthropic. **helPRs is the only AI code review tool that never touches your code.** This closes enterprise security reviews that stall competitors for months.

**Proven local concept.** helPRs is directly inspired by the challenge-me Claude Code plugin (v1.4.0), which implements the Socratic quiz loop locally and demonstrates that developers voluntarily engage with this approach. The plugin's scoring system (4 dimensions: Depth, Accuracy, Completeness, Insight; scale 0-10) and 12 normalized topic categories are battle-tested foundations that helPRs carries forward. The leap is from a local single-user CLI tool to a team-visible web product with mutual accountability.

**Data flywheel.** Over time, session data reveals which question patterns drive the best comprehension outcomes -- measured by score improvement over time and reduced post-merge incident rates. This creates a defensible moat that improves with scale.

## Who This Serves

**Primary: The PR author** -- a developer who wants to verify they understand the code before defending it in review. The aha moment: *"I can't answer a question about code I wrote myself."*

**Primary: The PR reviewer** -- a developer about to approve changes. The aha moment: *"I was about to LGTM a PR without understanding what it does."*

**Buyer: The engineering leader** (VP Eng, CTO, Tech Lead) -- wants quality and growth, not just velocity. Today they have no way to know if code reviews are done seriously. helPRs provides team learning culture and reduced production incidents from misunderstood code. Individual scores are never surfaced to managers -- the product builds understanding, not surveillance.

## Success Criteria

| Signal | Metric | Target |
|--------|--------|--------|
| Developers voluntarily engage | % of PRs with a started session | > 30% |
| Sessions are completed | Completion vs abandonment rate | > 60% |
| Developers return | Users engaging on 2+ consecutive PRs | > 40% |
| Comprehension improves | Average score at session 10 vs session 1, across 50+ dev cohorts | >= 15% improvement within 6 months |
| Developer satisfaction | Net Promoter Score | > 30 |

## Scope

**MVP (in scope):**
- GitHub App with PR webhook triggers (pull_request.opened, pull_request.synchronize)
- Web-based Socratic chat (run mode only -- one question at a time, interactive)
- Claude API integration (single LLM provider)
- Trial credits for first N sessions (no BYOK required to try the product)
- BYOK configuration for ongoing use
- Dynamic question generation from PR diffs
- Comprehension scoring (Depth, Accuracy, Completeness, Insight) with GitHub status check (informational, non-blocking)
- Score private by default; team-level opt-in for shared visibility
- Opinionated defaults (warm tone, feedback after each answer, scores private)
- GitHub OAuth authentication (seamless transition from PR comment to chat session)
- Instant demo mode (pre-loaded session on a famous open-source PR for zero-setup trial)
- Multi-language support (questions and interface adapt to user language)
- OpenCode-inspired design system (monospace-first, warm dark theme)
- Configurable bot behavior: suppress comments on PRs with specific labels (hotfix, urgent)

**Explicitly out of MVP:**
- MCQ / quiz mode
- Admin dashboard with advanced configuration
- Advanced progress tracking (recurring topics, growth curves)
- Onboarding via historical PRs
- Multi-LLM support
- Codebase indexing / RAG
- Manager-facing team analytics or individual score visibility
- Full self-hosted deployment

## Business Model

Per-seat pricing for private repositories. Free for public/open-source repos -- every helPRs session on a public PR is a free impression to every contributor and visitor, creating a compounding acquisition funnel. Trial credits included for first-time teams to remove the BYOK barrier to adoption.

Pricing positioned in the lower range of the market (~$8-15/user/month) reflecting the BYOK model where users provide their own API keys. Enterprise tier with SSO, audit logs, and custom question policies. Pricing strategy to be refined based on early adoption signals and willingness-to-pay research.

PLG motion: developer finds value personally on an open-source project, installs on their team's private repo, manager sees reduced production incidents and improved review quality, enterprise contract follows. The Slack/Linear adoption arc applied to code comprehension.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Bot fatigue -- developers ignore another PR bot | Opt-in model; configurable suppression on hotfix/urgent PRs; questions must surface blind spots a self-review cannot catch |
| Incumbents add comprehension features | Build data moat on question-response patterns; comprehension is orthogonal to their core defect-detection value prop; explore "Better Together" integrations with incumbents |
| BYOK limits unit economics | High-margin orchestration fee; trial credits for acquisition; value perception justifies per-seat fee alongside user-provided keys |
| Questions feel like interrogation, not learning | Warm tone by default; framing is empowerment ("understand your code better") not testing; actionable feedback teaches, not just evaluates |
| LLM hallucinations in questions | Clear disclaimer; report button; question data feeds prompt improvement. Prompt engineering quality is the core technical risk -- invest heavily before considering fine-tuning |
| Cultural backlash from visible scores | Scores private by default; never surfaced to managers; team-level visibility requires collective opt-in; status check is informational, never merge-blocking |
| Anthropic API single-provider dependency | Monitor for pricing/quality changes; architect for multi-LLM from day one even if MVP ships Claude-only |

## Vision

If helPRs succeeds, it defines a new category: **Comprehension-First Code Review**. AI coding tools are the engine; helPRs is the seatbelt -- the thing that lets teams go faster because they know someone understood what shipped.

The expansion path leads from PR comprehension to onboarding (learn a codebase through its PRs), continuous developer assessment, and compliance artifacts for regulated industries (timestamped comprehension attestations per PR). The adjacent developer assessment market ($30B, growing at 16.5% CAGR) provides significant expansion potential. Long-term vision to be refined as the product finds its market.
