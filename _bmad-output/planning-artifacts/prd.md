---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-02b-vision
  - step-02c-executive-summary
  - step-03-success
  - step-04-journeys
  - step-05-domain-skipped
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
inputDocuments:
  - product-brief-helprs.md
  - product-brief-helprs-distillate.md
  - research/domain-ai-pr-review-github-apps-research-2026-04-08.md
documentCounts:
  briefs: 2
  research: 1
  brainstorming: 0
  projectDocs: 0
workflowType: 'prd'
classification:
  projectType: saas_b2b
  domain: developer_tools_edtech
  complexity: medium
  projectContext: greenfield
---

# Product Requirements Document - helPRs

**Author:** Marius.pruvot
**Date:** 2026-04-08

## Executive Summary

helPRs is a GitHub App that creates Socratic LLM chat sessions for each pull request, challenging both the PR author and reviewer to prove they understand the code before it ships. For every PR, helPRs posts a session link where developers answer targeted questions from an AI acting as a senior staff engineer -- probing decisions, tradeoffs, and edge cases, not just correctness.

The product addresses comprehension debt: AI coding tools generate code 5-7x faster than developers can understand it, yet every existing AI code review tool (CodeRabbit, Copilot, Greptile, Qodo) competes on defect detection. None asks whether the person merging the code actually understands it. helPRs occupies this uncontested position -- "Wave 4" of AI code review: comprehension-oriented, complementary to any existing review tool.

helPRs is directly inspired by the challenge-me Claude Code plugin, a proven local prototype demonstrating that developers voluntarily engage with Socratic PR questioning. The leap is from a single-user CLI tool to a team-visible web product with mutual accountability.

Architecture: BYOK (Bring Your Own Key) with Claude API. helPRs is a pure orchestrator -- no source code is stored, indexed, or retained server-side. This zero-trust posture closes enterprise security reviews that stall competitors for months.

### What Makes This Special

The core value is not the score -- it's the moment of being challenged. Being forced to articulate *why* you made a decision, not just *that* it works. This transforms code review from a rubber-stamp gate into active learning.

helPRs is an empowerment tool, not a surveillance tool. It exists so developers keep mastery over their codebase as AI accelerates code generation. Score visibility is private by default; teams can configure shared visibility through admin settings when they choose transparency.

The dual challenge mechanic -- both author and reviewer are questioned at different depth levels -- turns code review from a one-directional approval into a bilateral comprehension contract. No other tool does this.

## Project Classification

| Dimension | Value |
|-----------|-------|
| **Project Type** | SaaS B2B |
| **Domain** | Developer Tools (EdTech-adjacent) |
| **Complexity** | Medium |
| **Project Context** | Greenfield |

## Success Criteria

### User Success

- Developer completes a session and identifies at least one blind spot they hadn't considered
- Session feels like preparation for review, not interrogation -- warm, empowering tone
- Developer returns voluntarily on their next PR without being prompted
- Reviewer engages with their challenge before approving, not after

### Business Success

| Metric | Target | Timeframe |
|--------|--------|-----------|
| Repos connected (free + paid) | 100+ | 3 months post-launch |
| PRs with a started session | > 30% of eligible PRs | 6 months |
| Session completion rate | > 60% | Ongoing |
| Return usage (2+ consecutive PRs) | > 40% of users | 6 months |
| Paid teams (private repos) | 10+ | 3 months |
| NPS from developers | > 30 | 6 months |

### Technical Success

| Metric | Target |
|--------|--------|
| Time to first question after session open | < 3s |
| Streaming response latency (first token) | < 1s |
| Question report rate (flagged as bad/irrelevant) | < 5% |
| Session availability (uptime) | > 99.5% |
| Webhook processing time (PR event to comment posted) | < 10s |

### Measurable Outcomes

- Comprehension score at session 10 >= 15% higher than session 1, across cohorts of 50+ developers, within 6 months
- Cross-pollination: developers who use helPRs on one repo request installation on other repos
- Organic word-of-mouth: new installations traceable to existing users (referral signal)

## User Journeys

### Journey 1: The PR Author -- "I wrote it, but do I understand it?"

**Persona:** Karim, mid-level backend developer. Uses Copilot daily, ships 3-4 PRs per week. Fast, productive, but sometimes merges code he generated without fully grasping the edge cases.

**Opening Scene:** Karim opens a PR for a new retry mechanism in the payment service. He wrote 60% of it, Copilot generated the rest. He's about to tag a reviewer when he sees a new comment from helPRs: a link to his comprehension session.

**Rising Action:** He clicks through, authenticates via GitHub OAuth, and lands in the chat. Split view: chat on the left, his diff on the right. The first question hits: "Your retry logic uses exponential backoff with jitter -- what happens if the downstream service returns a 429 with a Retry-After header? Does your implementation respect it?" Karim pauses. He hadn't thought about that. He checks the diff, realizes the generated code ignores the header entirely.

**Climax:** Question 4 asks about the interaction between his retry mechanism and the circuit breaker already in the codebase. Karim realizes he didn't know there was a circuit breaker. He answers honestly, gets immediate feedback with a link to the relevant file. The session taught him something concrete about his own codebase.

**Resolution:** Karim finishes the session with a 6.5/10 score. He updates his PR to handle Retry-After and coordinate with the existing circuit breaker before requesting human review. His reviewer later comments: "This is unusually thorough for a retry PR."

### Journey 2: The PR Reviewer -- "I was about to LGTM without understanding"

**Persona:** Priya, senior frontend engineer. Reviews 5-8 PRs per week across two teams. Thorough on frontend PRs, but rubber-stamps backend changes she's less familiar with.

**Opening Scene:** Priya is assigned to review a PR that refactors the authentication middleware. She opens the diff, scans it -- looks clean, well-structured. She's about to approve when she notices the helPRs session link for reviewers.

**Rising Action:** She opens the reviewer session. The questions are different from what the author got -- they probe her understanding of what the changes do, not why they were made. "This PR removes the session validation middleware from three routes. What user-facing behavior changes as a result?" Priya realizes she doesn't know which routes are affected or what the middleware was protecting.

**Climax:** She scores 4/10 on the reviewer challenge. The feedback shows her which questions she missed and links to the relevant code sections. She goes back to the PR with specific questions for the author instead of a generic LGTM.

**Resolution:** The review conversation that follows is the most productive one she's had in months. She catches a security issue the author hadn't considered either. Both learn something.

### Journey 3: The Engineering Leader -- "Are my teams actually understanding what they ship?"

**Persona:** David, VP of Engineering at a 40-person startup. Tracks DORA metrics religiously but has a nagging feeling that velocity is masking comprehension problems. Last month, a production incident traced back to AI-generated code nobody understood.

**Opening Scene:** David hears about helPRs from one of his tech leads who tried it on a personal project. He's intrigued by the concept but skeptical of another PR bot.

**Rising Action:** He asks two volunteer teams to install helPRs for a month. He doesn't see individual scores (they're private), but he notices the teams' review conversations becoming more substantive. PRs get fewer "LGTM" comments and more technical discussion.

**Climax:** After a month, one tech lead reports: "The juniors are asking better questions in review. They're engaging with the code instead of rubber-stamping." David sees reduced post-merge hotfixes on the pilot teams.

**Resolution:** David rolls out helPRs org-wide. He doesn't mandate it -- he recommends it. The PLG loop closes: developer finds value, team adopts, leader sees results.

### Journey 4: The Admin -- "Set it up for the team"

**Persona:** Sasha, tech lead and de facto DevOps person. Responsible for installing and configuring tools for a 12-person engineering team.

**Opening Scene:** David asks Sasha to set up helPRs for the team. Sasha goes to the helPRs website, clicks "Install GitHub App."

**Rising Action:** GitHub OAuth flow redirects to org selection. Sasha chooses org-level installation and selects specific repositories. Back on helPRs, she's prompted to enter the team's Anthropic API key (BYOK). She pastes the key, sets the per-seat plan for 12 developers.

**Climax:** Sasha configures bot suppression: PRs labeled "hotfix" or "urgent" won't get helPRs comments. She sets score visibility to private (default). The setup takes under 10 minutes.

**Resolution:** The next PR on the team triggers a helPRs comment automatically. Sasha shares the demo session link in the team Slack channel so everyone can try it before their first real session.

### Journey 5: The Demo Visitor -- "Show me in 60 seconds"

**Persona:** Alex, curious developer who saw helPRs mentioned in a tweet. Has never used the product.

**Opening Scene:** Alex lands on the helPRs homepage. They see a "Try the demo" button -- no signup, no API key needed.

**Rising Action:** One click opens a pre-loaded session on a famous open-source PR. Alex sees the split view: chat on the left, real diff on the right. The first question appears immediately, asking about a design decision in the PR.

**Climax:** Alex answers two questions, gets instant feedback. The experience is fast, the questions are genuinely interesting. Alex thinks: "I wish I had this on my last PR."

**Resolution:** Alex clicks "Install on your repo" from the demo page. GitHub OAuth flow begins. Time from landing to first real session: under 5 minutes.

### Journey Requirements Summary

| Journey | Key Capabilities Revealed |
|---------|--------------------------|
| PR Author | Webhook triggers, question generation from diff, SSE chat, scoring, feedback per question, code linking in feedback |
| PR Reviewer | Separate reviewer session with different question types, reviewer-specific scoring, session linking from PR comment |
| Engineering Leader | Private-by-default scores, team-level adoption visibility (not individual scores), PLG onboarding flow |
| Admin | GitHub App installation (org/repo level), BYOK API key configuration, per-seat billing setup, bot suppression config, score visibility settings |
| Demo Visitor | Pre-loaded demo session (no auth required), zero-friction trial, conversion CTA to installation flow |

## SaaS B2B Specific Requirements

### Tenant Model

One tenant = one GitHub App installation. An installation can be org-level (covering selected or all repos) or repo-level (single repo). Each installation has its own BYOK API key, billing configuration, and settings.

A GitHub user can participate in sessions across multiple installations (e.g., as an employee in org A and an OSS contributor on repo B). User identity is GitHub-native -- no separate helPRs account. Session data is scoped to the installation that triggered it.

### Permission Model (RBAC)

| Role | Source | Capabilities |
|------|--------|-------------|
| **Installation Admin** | GitHub user who installed the app (GitHub org admin or repo admin) | Configure BYOK API key, manage billing (per-seat), set bot suppression labels, set score visibility default, view installation settings |
| **Developer** | Any GitHub user with access to a repo where helPRs is installed | Start and complete sessions (author or reviewer), view own scores, report questions, provide feedback |
| **Demo Visitor** | Anonymous / unauthenticated | Access pre-loaded demo session only, no persistent data |

No manager role in MVP. No ability for admins to view individual developer scores. Score visibility settings affect whether developers can see each other's scores, not whether admins can see them.

### Subscription & Billing

| Tier | Repos | BYOK | Price |
|------|-------|------|-------|
| **Free** | Public repos only | Required | $0 |
| **Team** | Private repos | Required | $8-15/seat/month |
| **Enterprise** (post-MVP) | Private repos + SSO + audit logs | Required | Custom pricing |

Billing is per-seat per installation. A "seat" is a GitHub user who has started at least one session in the billing period. Inactive users are not billed. BYOK is required at all tiers -- helPRs never proxies LLM calls through its own keys.

### Integration Points (MVP)

| Integration | Type | Purpose |
|-------------|------|---------|
| **GitHub App** | Webhooks (incoming) | Receive PR events (pull_request.opened, pull_request.synchronize) |
| **GitHub API** | REST (outgoing) | Fetch diffs, file contents, post PR comments, set status checks |
| **GitHub OAuth** | Auth flow | Authenticate users seamlessly from PR comment to chat session |
| **Anthropic Claude API** | REST (outgoing, user's key) | Generate Socratic questions, evaluate answers, produce scores |

No Slack, no outgoing webhooks, no other integrations in MVP.

### Compliance Requirements (MVP)

- GDPR-compliant privacy policy and cookie consent on web interface
- Zero-retention on LLM API calls (Anthropic API default)
- No source code stored server-side -- diffs are processed in-memory and sent to LLM via user's BYOK key
- BYOK API keys encrypted at rest
- HMAC SHA-256 webhook signature verification on all incoming GitHub events
- EU AI Act Article 50 transparency: all AI-generated content (questions, feedback, scores) clearly labeled as AI-produced

### Implementation Considerations

- GitHub App permissions: read-only access to PR diffs and file contents, write access limited to PR comments and status checks
- Installation access tokens (scoped per installation) for all GitHub API calls -- never app-level credentials
- Session data retention: metadata only (scores, topics, timestamps, question hashes). No verbatim questions/answers stored long-term
- Rate limiting on session creation (max 50 sessions/day per installation)

## Innovation & Novel Patterns

### Detected Innovation Areas

**Category Creation -- Comprehension-First Code Review.** Every AI code review tool competes on defect detection accuracy. helPRs creates a new category: comprehension-oriented review. This is not a better version of existing tools -- it solves a different problem entirely.

**Dual Comprehension Contract.** No existing tool challenges both the PR author and the reviewer. helPRs turns code review from a one-directional approval gate into a bilateral accountability mechanism.

**Socratic LLM as Senior Staff Engineer.** Using an LLM not to find bugs or suggest fixes, but to ask questions that probe understanding. The AI never touches the code -- it only asks questions about it. This inverts the typical AI code tool paradigm.

**Proven Local-to-Web Pattern.** The challenge-me Claude Code plugin validates the core hypothesis locally. helPRs is the productization leap: from single-user CLI to team-visible web product.

### Market Context & Competitive Landscape

The AI code review market is ~$4B with 26-45% CAGR. Over 1.3M repos use AI code review tools. Yet comprehension debt is worsening: AI generates code 5-7x faster than humans understand it, and controlled studies show 17% lower comprehension scores with AI assistance. No incumbent addresses this gap.

### Validation Approach

- **Hypothesis:** Developers voluntarily engage with Socratic PR questioning and improve comprehension over time
- **Local validation:** challenge-me plugin demonstrates voluntary engagement in CLI context
- **MVP validation:** Track session start rate (>30% of PRs), completion rate (>60%), and return usage (>40% on consecutive PRs)
- **Comprehension validation:** Measure score improvement across first 10 sessions per developer cohort
- **Question quality validation:** Report rate <5%, post-session feedback (thumbs up/down)

### Risk Mitigation

| Innovation Risk | Mitigation |
|----------------|------------|
| Developers don't see value in being questioned | Demo mode proves value in 60 seconds; warm empowering tone; opt-in only |
| Questions are too generic or hallucinated | Heavy prompt engineering investment (challenge-me SKILL.md as foundation); report button; feedback loop |
| Category doesn't resonate with buyers | Position as complement to existing tools, not replacement |
| Incumbents copy the feature | Data moat on question-response patterns; comprehension is orthogonal to their core value prop |

## Product Scope & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Experience MVP -- the core value is the Socratic challenge experience. A developer must feel the "aha" moment within their first session. Everything else is infrastructure to deliver that moment.

**Resource Requirements:** 2-person team. This constrains MVP scope to the essential experience loop: PR triggers session, developer answers questions, developer gets score and feedback.

**Prompt Engineering Foundation:** The challenge-me Claude Code plugin's run SKILL.md (~220 lines) is a battle-tested Socratic prompt. helPRs adapts this prompt for the web context (injecting diff + repo metadata instead of local CLI context). This is the single highest-leverage asset for MVP quality.

### MVP Feature Set (Phase 1)

**Core User Journeys Supported:**
- Journey 1 (PR Author) -- full support
- Journey 2 (PR Reviewer) -- full support
- Journey 5 (Demo Visitor) -- full support
- Journey 4 (Admin) -- minimal: install app, configure BYOK key, basic suppression labels. No billing UI (manual/Stripe checkout link)
- Journey 3 (Engineering Leader) -- indirect only: leader sees effect through team behavior, no dedicated dashboard

**Must-Have Capabilities:**

| Capability | Rationale |
|-----------|-----------|
| GitHub App webhook handler | Without it, nothing triggers |
| PR comment with session link (author + reviewer) | Entry point to the product |
| GitHub OAuth authentication | Seamless transition from PR to session |
| Web chat with SSE streaming (split view: chat + diff) | The core experience |
| Socratic question generation from diff (adapted from challenge-me run SKILL.md) | The product's soul |
| Dynamic question count (3-5 / 5-7 / 7-10 based on PR size) | Right-sized challenge |
| Feedback after each answer (gap identification + code links) | Teaching moment |
| Comprehension scoring (Depth, Accuracy, Completeness, Insight) | Session outcome |
| GitHub status check (informational, non-blocking) | Visibility on PR |
| Score private by default | Trust and adoption |
| BYOK API key configuration per installation | Business model |
| Demo mode (pre-loaded session, no auth required) | Zero-friction trial |
| Report button per question | Quality feedback loop |
| Bot suppression via PR labels | Respect developer workflow |

**Explicitly Deferred from MVP (2-person scope constraint):**

| Feature | Why Deferred |
|---------|-------------|
| Admin dashboard | Opinionated defaults replace configuration UI. Settings via API or minimal settings page |
| Per-seat billing UI | Use Stripe checkout link or manual setup. No complex billing portal |
| Multi-language support | English-first. LLM naturally handles multi-language but UI/prompts are English only |
| Session analytics / progress tracking | Track data from day one, but no UI to display it yet |
| Adaptive difficulty | Static difficulty based on PR size is sufficient for MVP |
| Team-level score visibility opt-in | Private-only in MVP. Team visibility comes with admin dashboard |

### Phase 2 -- Growth (months 2-4)

- Admin dashboard with team configuration (tone, visibility, suppression rules, BYOK management)
- Per-seat billing UI (Stripe integration, seat counting, invoicing)
- Multi-language support (UI + prompts)
- Session analytics and progress tracking per developer
- Adaptive difficulty (TreeInstruct-inspired state tracking)
- Re-trigger on new push with adapted questions based on delta
- Multi-dimension question tagging (architecture, testing, security, design)

### Phase 3 -- Scale (months 4-8)

- Multi-agent question generation (specialized agents per dimension)
- Optional codebase context via lightweight RAG (for cross-file questions)
- Gamification (streaks, team leaderboards, comprehension badges)
- Enterprise features (SSO, audit logs, custom question policies)
- Onboarding tool (learn a codebase through its PRs)
- Multi-LLM support
- GitLab / Azure DevOps / Bitbucket support

### Risk Mitigation Strategy

**Technical Risk -- Question quality:**
- Mitigation: Start from proven challenge-me SKILL.md prompt. Iterate using report button data before adding complexity. Prompt engineering quality is the #1 technical investment.
- Contingency: If quality is insufficient at launch, focus all sprint capacity on prompt iteration before building features.

**Market Risk -- Developer adoption:**
- Mitigation: Demo mode provides zero-friction proof of value. Free on public repos creates organic acquisition. Opt-in model avoids backlash.
- Contingency: If session start rate is <15% after 3 months, pivot from bot-initiated to developer-initiated sessions (badge in PR instead of comment).

**Resource Risk -- 2-person team:**
- Mitigation: Defer all non-essential features. No admin dashboard, no billing UI, no analytics UI in MVP. Use opinionated defaults instead of configuration surfaces.
- Contingency: If MVP takes longer than 6 weeks, cut demo mode. Ship core loop only: webhook -> chat -> score -> status check.

## Functional Requirements

### Session Lifecycle

- FR1: The system can receive GitHub webhook events (pull_request.opened, pull_request.synchronize) and create a comprehension session for the PR
- FR2: The system can post a PR comment containing session links for both author and reviewer roles
- FR3: The system can suppress PR comments on PRs matching configured labels (e.g., hotfix, urgent)
- FR4: A developer can authenticate via GitHub OAuth to access their session from a PR comment link
- FR5: A developer can view their session in a split-view interface (chat on left, PR diff on right)

### Socratic Challenge

- FR6: The system can generate Socratic comprehension questions from a PR diff, adapted to PR size (3-5 for small <100 lines, 5-7 for medium 100-500, 7-10 for large >500)
- FR7: The system can generate different question types based on role: author questions probe decisions, tradeoffs, and edge cases; reviewer questions probe understanding of what the changes do and their impact
- FR8: The system can deliver questions one at a time with real-time streaming, waiting for the developer's answer before presenting the next question
- FR9: The system can provide feedback after each answer, identifying comprehension gaps and linking to relevant code sections in the diff
- FR10: The system can generate questions that go beyond the diff content -- probing callers, consumers, architectural decisions, and system-level impact
- FR11: The system can handle large PRs (2000+ lines) by selecting files with the highest line-change count for detailed analysis and providing stats on all files

### Scoring & Feedback

- FR12: The system can evaluate developer answers and produce a comprehension score across four dimensions: Depth, Accuracy, Completeness, and Insight (scale 0-10)
- FR13: The system can produce a verdict based on score: Exceptional (9-10), Strong (7-8), Adequate (5-6), Weak (3-4), Insufficient (0-2)
- FR14: The system can post a GitHub status check with the comprehension score (informational, never merge-blocking)
- FR15: A developer can view their own comprehension score and detailed feedback after completing a session
- FR16: The system can default score visibility to private, visible only to the session participant

### Question Quality

- FR17: A developer can report a question as bad or irrelevant via a report button
- FR18: A developer can provide post-session feedback (thumbs up/down and optional comment)
- FR19: The system can display a disclaimer that questions are AI-generated and may contain inaccuracies

### Installation & Configuration

- FR20: An admin can install the helPRs GitHub App at org-level or repo-level
- FR21: An admin can configure a BYOK Anthropic API key for their installation
- FR22: An admin can configure bot suppression labels for their installation
- FR23: An admin can view their installation settings and current configuration
- FR24: The system can validate the BYOK API key on configuration and report errors

### Authentication & Authorization

- FR25: A developer can authenticate using their GitHub identity -- no separate helPRs account required
- FR26: The system can verify that a developer has access to the repository associated with a session before granting access
- FR27: The system can restrict installation settings to the admin who installed the app (GitHub org/repo admin)

### Demo Experience

- FR28: A visitor can access a pre-loaded demo session without authentication or API key
- FR29: A visitor can experience the full Socratic challenge flow (questions, answers, feedback, scoring) in the demo
- FR30: A visitor can navigate from the demo to the GitHub App installation flow

### Billing

- FR31: The system can distinguish between public repos (free) and private repos (paid) for billing purposes
- FR32: An admin can access a payment flow for private repo usage
- FR33: The system can track seat usage per installation (GitHub users who started at least one session in the billing period)

### Data & Privacy

- FR34: The system can send PR diffs to the Anthropic Claude API using the installation's BYOK key with zero-retention
- FR35: The system can store session metadata (scores, topics, timestamps) without storing verbatim questions or source code
- FR36: The system can encrypt BYOK API keys at rest
- FR37: The system can verify incoming GitHub webhook signatures using cryptographic signing
- FR38: The system can label all AI-generated content (questions, feedback, scores) as AI-produced

## Non-Functional Requirements

### Performance

| Metric | Target | Context |
|--------|--------|---------|
| Webhook processing (PR event to comment posted) | < 10s | Developer sees helPRs comment shortly after opening PR |
| Time to first question after session open | < 3s | Developer must not wait on a blank screen |
| Streaming latency (first token) | < 1s | Chat must feel conversational, not batch |
| Answer evaluation + feedback generation | < 5s | Feedback must appear quickly after answer submission |
| Score computation and GitHub status check posting | < 10s after last answer | Session conclusion must feel immediate |
| Demo session load time | < 2s | Zero-friction trial demands instant load |
| Web interface initial load (cold start) | < 3s on 4G connection | No heavy framework penalty |

### Security

- All data in transit encrypted via TLS 1.2+
- BYOK API keys encrypted at rest using industry-standard encryption
- GitHub webhook payloads verified using cryptographic signature verification -- reject unverified payloads
- GitHub OAuth tokens stored securely, scoped to minimum required permissions
- Installation access tokens used for all GitHub API calls -- never app-level credentials
- No source code stored server-side at any point -- diffs processed in-memory only
- Session metadata stored without verbatim questions or answers
- Rate limiting on session creation (max 50 sessions/day per installation) and authentication endpoints
- CORS policy restricting API access to helPRs domains only

### Scalability

- System supports 100+ concurrent installations while maintaining all performance targets defined above
- Architecture allows horizontal scaling of webhook processing and chat session handling independently
- No single-tenant bottleneck: one installation's heavy usage does not impact other installations
- Database queries for session metadata return results in under 500ms at p95 for datasets up to 1M sessions

### Reliability

- Service availability target: 99.5% uptime
- Graceful degradation when Anthropic API is unavailable: clear error message, allow retry, never lose session state
- Graceful degradation when GitHub API is unavailable: queue webhook processing, retry with exponential backoff
- Session state survives server restarts (no in-memory-only session state)
