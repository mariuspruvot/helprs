---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
status: complete
completedAt: '2026-04-09'
inputDocuments:
  - prd.md
  - architecture.md
  - ux-design-specification.md
  - design/DESIGN.md
  - design/README.md
---

# helPRs - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for helPRs, decomposing the requirements from the PRD, UX Design, Architecture, and Design System into implementable stories.

## Requirements Inventory

### Functional Requirements

- FR1: The system can receive GitHub webhook events (pull_request.opened, pull_request.synchronize) and create a comprehension session for the PR
- FR2: The system can post a PR comment containing session links for both author and reviewer roles
- FR3: The system can suppress PR comments on PRs matching configured labels (e.g., hotfix, urgent)
- FR4: A developer can authenticate via GitHub OAuth to access their session from a PR comment link
- FR5: A developer can view their session in a split-view interface (chat on left, PR diff on right)
- FR6: The system can generate Socratic comprehension questions from a PR diff, adapted to PR size (3-5 for small <100 lines, 5-7 for medium 100-500, 7-10 for large >500)
- FR7: The system can generate different question types based on role: author questions probe decisions, tradeoffs, and edge cases; reviewer questions probe understanding of what the changes do and their impact
- FR8: The system can deliver questions one at a time with real-time streaming, waiting for the developer's answer before presenting the next question
- FR9: The system can provide feedback after each answer, identifying comprehension gaps and linking to relevant code sections in the diff
- FR10: The system can generate questions that go beyond the diff content -- probing callers, consumers, architectural decisions, and system-level impact
- FR11: The system can handle large PRs (2000+ lines) by selecting files with the highest line-change count for detailed analysis and providing stats on all files
- FR12: The system can evaluate developer answers and produce a comprehension score across four dimensions: Depth, Accuracy, Completeness, and Insight (scale 0-10)
- FR13: The system can produce a verdict based on score: Exceptional (9-10), Strong (7-8), Adequate (5-6), Weak (3-4), Insufficient (0-2)
- FR14: The system can post a GitHub status check with the comprehension score (informational, never merge-blocking)
- FR15: A developer can view their own comprehension score and detailed feedback after completing a session
- FR16: The system can default score visibility to private, visible only to the session participant
- FR17: A developer can report a question as bad or irrelevant via a report button
- FR18: A developer can provide post-session feedback (thumbs up/down and optional comment)
- FR19: The system can display a disclaimer that questions are AI-generated and may contain inaccuracies
- FR20: An admin can install the helPRs GitHub App at org-level or repo-level
- FR21: An admin can configure a BYOK Anthropic API key for their installation
- FR22: An admin can configure bot suppression labels for their installation
- FR23: An admin can view their installation settings and current configuration
- FR24: The system can validate the BYOK API key on configuration and report errors
- FR25: A developer can authenticate using their GitHub identity -- no separate helPRs account required
- FR26: The system can verify that a developer has access to the repository associated with a session before granting access
- FR27: The system can restrict installation settings to the admin who installed the app (GitHub org/repo admin)
- FR28: A visitor can access a pre-loaded demo session without authentication or API key
- FR29: A visitor can experience the full Socratic challenge flow (questions, answers, feedback, scoring) in the demo
- FR30: A visitor can navigate from the demo to the GitHub App installation flow
- FR31: The system can distinguish between public repos (free) and private repos (paid) for billing purposes
- FR32: An admin can access a payment flow for private repo usage
- FR33: The system can track seat usage per installation (GitHub users who started at least one session in the billing period)
- FR34: The system can send PR diffs to the Anthropic Claude API using the installation's BYOK key with zero-retention
- FR35: The system can store session metadata (scores, topics, timestamps) without storing verbatim questions or source code
- FR36: The system can encrypt BYOK API keys at rest
- FR37: The system can verify incoming GitHub webhook signatures using cryptographic signing
- FR38: The system can label all AI-generated content (questions, feedback, scores) as AI-produced

### NonFunctional Requirements

- NFR1: Webhook processing (PR event to comment posted) < 10s
- NFR2: Time to first question after session open < 3s
- NFR3: Streaming latency (first token) < 1s
- NFR4: Answer evaluation + feedback generation < 5s
- NFR5: Score computation and GitHub status check posting < 10s after last answer
- NFR6: Demo session load time < 2s
- NFR7: Web interface initial load (cold start) < 3s on 4G connection
- NFR8: All data in transit encrypted via TLS 1.2+
- NFR9: BYOK API keys encrypted at rest using industry-standard encryption
- NFR10: GitHub webhook payloads verified using cryptographic signature verification -- reject unverified payloads
- NFR11: GitHub OAuth tokens stored securely, scoped to minimum required permissions
- NFR12: Installation access tokens used for all GitHub API calls -- never app-level credentials
- NFR13: No source code stored server-side at any point -- diffs processed in-memory only
- NFR14: Session metadata stored without verbatim questions or answers
- NFR15: Rate limiting on session creation (max 50 sessions/day per installation) and authentication endpoints
- NFR16: CORS policy restricting API access to helPRs domains only
- NFR17: System supports 100+ concurrent installations while maintaining all performance targets
- NFR18: Architecture allows horizontal scaling of webhook processing and chat session handling independently
- NFR19: No single-tenant bottleneck: one installation's heavy usage does not impact other installations
- NFR20: Database queries for session metadata return results in under 500ms at p95 for datasets up to 1M sessions
- NFR21: Service availability target: 99.5% uptime
- NFR22: Graceful degradation when Anthropic API is unavailable: clear error message, allow retry, never lose session state
- NFR23: Graceful degradation when GitHub API is unavailable: queue webhook processing, retry with exponential backoff
- NFR24: Session state survives server restarts (no in-memory-only session state)

### Additional Requirements

_From Architecture document:_

- AR1: Composable custom setup (no starter template) -- project scaffolding as first implementation story with monorepo structure (apps/api, apps/web, infra)
- AR2: Python 3.12+ / FastAPI 0.135.3 backend with SQLAlchemy 2.0 async ORM, Alembic migrations, Pydantic v2
- AR3: Pydantic AI 1.77.0 for LLM agent framework (question_agent, feedback_agent, scoring_agent) -- replaces custom LLM adapter
- AR4: Astral toolchain: uv for package management, ruff 0.15+ for linting/formatting
- AR5: React 19 + TypeScript frontend with Vite 8 (Rolldown bundler), React Router 7, Zustand 5, TanStack Query 5
- AR6: PostgreSQL as sole data store (no Redis in MVP), Docker + Docker Compose, Coolify deployment on Kimsufi
- AR7: DDD hybrid data modeling: full DDD layers for comprehension module (domain/application/infrastructure/presentation), flat structure for supporting modules (installation, identity, billing, webhook)
- AR8: JWT + Refresh Token authentication (15 min JWT + httpOnly cookie refresh token)
- AR9: Fernet symmetric encryption for BYOK API keys (master key from env var)
- AR10: FastAPI BackgroundTasks + DB persistence for webhook processing (persist event to DB → return 200 → process in background)
- AR11: slowapi middleware for rate limiting (per-installation 50 sessions/day + per-IP auth endpoint protection)
- AR12: Domain exception hierarchy mapped to HTTP responses via global exception handler
- AR13: Feature-based frontend structure (features/session, features/demo, features/auth, features/installation, features/landing + shared/)
- AR14: Custom SSE hook (useSSE) with reconnection, event type parsing, Zustand integration
- AR15: GitHub Actions CI/CD pipeline (lint → test → build → push)
- AR16: structlog JSON structured logging with correlation IDs (session_id, installation_id)
- AR17: Sentry error tracking (free tier)
- AR18: Type sharing via OpenAPI auto-generation → openapi-typescript for frontend types
- AR19: SQLAdmin 0.24.0 for internal admin panel
- AR20: Lemon Squeezy as payment provider / merchant of record (handles VAT/tax)

### UX Design Requirements

- UX-DR1: Implement design token pipeline -- CSS custom properties (`:root`) as source of truth → Tailwind config mapping → optional TypeScript constants. Tokens cover colors (primary, semantic, border), typography (Berkeley Mono + IBM Plex Mono fallback), spacing (8px grid), border radius (4px default, 6px inputs), and elevation (flat, border-only depth)
- UX-DR2: Build split-view session layout -- chat panel (~60% default) on left, diff panel (~40%) on right, with draggable resize handle (4px visual, 12px hit area). Max chat message width 720px. Collapse to tabbed interface below 1100px, chat-only below 768px with "Open on desktop" banner
- UX-DR3: Build chat message components -- AI message (markdown-rendered, streaming-aware, code link support), User message (plain text, `#302c2c` background distinction), with 8px message gap, 16px question-to-feedback gap. Streaming token-by-token with prefers-reduced-motion support (show full message at once)
- UX-DR4: Build chat input component -- fixed bottom, 48px minimum height with auto-expand, 16px padding, Enter to submit, Shift+Enter for newline. Input disabled during feedback generation
- UX-DR5: Build diff viewer panel -- unified diff format with syntax highlighting, line numbers, file tabs (14px weight 500, active tab bold 700), scroll-to-line-and-highlight API for code links (highlight: `rgba(0, 122, 255, 0.15)`), read-only mode (no commenting/editing), `#302c2c` background
- UX-DR6: Implement cross-panel code linking -- clickable code references in chat feedback scroll and highlight diff panel lines. Hover preview (subtle highlight without scrolling). Active file tab highlighted with accent blue when question references specific code
- UX-DR7: Build session header component -- repo name (16px bold), PR title (16px regular), role badge (Author: accent blue 15% opacity bg / Reviewing: warning orange 15% opacity bg, 12px uppercase medium weight), progress indicator ("Question N of M", 14px gray, aria-live="polite"), AI disclaimer (12px muted). Fixed 48px height with 12px vertical padding
- UX-DR8: Build score card component -- inline in chat at session end, 4 horizontal dimension bars (Depth: accent blue, Accuracy: success green, Completeness: warning orange, Insight: `#ff3b30` warm accent), verdict badge with color mapping (Exceptional: green, Strong: blue, Adequate: gray, Weak/Insufficient: warning orange -- never red for scores), gap summary as "Areas to deepen", 24px padding. ARIA labels for all dimension values
- UX-DR9: Build question report UI -- small flag icon on each AI question message. One click opens minimal "Why is this question problematic?" selector. No interruption to conversation flow. `#6e6e73` muted color
- UX-DR10: Build post-session feedback UI -- thumbs up/down + optional comment, appears below score card. Not intrusive
- UX-DR11: Build demo session page -- pre-loaded famous OSS PR, no authentication required, shorter session (2-3 questions), identical split-view. Contextual CTA after score card: "Install on your repo" leading to GitHub App installation flow
- UX-DR12: Build landing page -- hero section with value prop + "Try the demo" CTA, "How it works" section, pricing section (free/team tiers), social proof area. OpenCode-inspired terminal-native aesthetic
- UX-DR13: Build admin setup page (SetupView) -- single primary task: BYOK API key input with validation (success/error states). Optional bot suppression labels with defaults (hotfix, urgent, trivial). Setup complete summary with connected repos, valid key confirmation, and next steps
- UX-DR14: Build installation settings page (SettingsView) -- view current configuration, update API key, manage suppression labels
- UX-DR15: Implement GitHub OAuth callback component -- handle redirect from GitHub, store JWT, redirect to session. Transparent for returning users (zero clicks)
- UX-DR16: Implement protected route component -- auth guard that redirects unauthenticated users to OAuth flow
- UX-DR17: Implement keyboard accessibility throughout -- Tab navigation for all interactive elements, Enter to activate code links and report button, arrow keys for resize handle and file tab navigation. Focus states using border-based indicators (no shadow rings)
- UX-DR18: Implement screen reader support -- AI messages with "helPRs asks:" prefix, user messages with "You answered:", feedback with "Feedback:" prefix, ARIA labels on score card dimensions and verdict, aria-live for progress updates, descriptive aria-label on code links
- UX-DR19: Implement error handling UX -- LLM timeout: "Taking a moment to think..." with auto-retry after 5s then "Connection issue. Your progress is saved." Invalid BYOK key: clear error before session loads. Connection loss: "Reconnecting..." with local answer queue. Empty LLM response: skip question with note
- UX-DR20: Implement optimistic UI patterns -- developer's answer appears immediately in chat before server response. No visible "processing" state between answer and feedback streaming. Skeleton states only for operations > 1s

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 2 | Webhook reception (PR opened/synchronize) |
| FR2 | Epic 2 | PR comment posting with session links |
| FR3 | Epic 2 | Bot suppression via configured labels |
| FR4 | Epic 1 | GitHub OAuth authentication |
| FR5 | Epic 3 | Split-view UI (chat + diff) |
| FR6 | Epic 3 | Socratic question generation from diffs |
| FR7 | Epic 3 | Role-based question types (author vs reviewer) |
| FR8 | Epic 3 | Real-time streaming question delivery |
| FR9 | Epic 3 | Per-answer feedback with code links |
| FR10 | Epic 3 | Beyond-diff probing questions |
| FR11 | Epic 3 | Large PR handling (2000+ lines) |
| FR12 | Epic 4 | 4-dimension comprehension scoring |
| FR13 | Epic 4 | Verdict system (Exceptional → Insufficient) |
| FR14 | Epic 4 | GitHub status check posting |
| FR15 | Epic 4 | Score + feedback visibility |
| FR16 | Epic 4 | Private-by-default scores |
| FR17 | Epic 4 | Question report button |
| FR18 | Epic 4 | Post-session feedback (thumbs + comment) |
| FR19 | Epic 3 | AI-generated disclaimer display |
| FR20 | Epic 1 | GitHub App install (org/repo) |
| FR21 | Epic 1 | BYOK API key configuration |
| FR22 | Epic 1 | Bot suppression label configuration |
| FR23 | Epic 1 | Installation settings view |
| FR24 | Epic 1 | BYOK key validation on config |
| FR25 | Epic 1 | GitHub-native identity (no separate account) |
| FR26 | Epic 1 | Repo access verification |
| FR27 | Epic 1 | Admin role restriction for settings |
| FR28 | Epic 5 | Pre-loaded demo session (no auth) |
| FR29 | Epic 5 | Full Socratic demo flow |
| FR30 | Epic 5 | Demo to install conversion CTA |
| FR31 | Epic 6 | Public/private repo distinction |
| FR32 | Epic 6 | Payment flow for private repos |
| FR33 | Epic 6 | Per-seat usage tracking |
| FR34 | Epic 3 | BYOK zero-retention LLM calls |
| FR35 | Epic 3 | Metadata-only session storage |
| FR36 | Epic 1 | BYOK key encryption at rest |
| FR37 | Epic 1 | Webhook signature verification |
| FR38 | Epic 3 | AI content labeling |

## Epic List

### Epic 1: GitHub App Installation & Identity
Admins can install the helPRs GitHub App on their org/repo, configure their BYOK Anthropic API key, and developers can authenticate via GitHub OAuth. Includes project scaffolding, core infrastructure, identity module, installation module, and admin UI.
**FRs covered:** FR4, FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR27, FR36, FR37

### Epic 2: Webhook Processing & Session Lifecycle
When a developer opens a PR, helPRs automatically creates a comprehension session and posts a PR comment with session links for both author and reviewer roles. Supports bot suppression via configured labels.
**FRs covered:** FR1, FR2, FR3

### Epic 3: Socratic Comprehension Experience
A developer can engage in a full Socratic comprehension session — AI-generated questions streaming in real-time, answers with per-question feedback, code-linked diff navigation in a split-view interface. Questions adapt to role (author/reviewer) and PR size, with beyond-diff probing for depth.
**FRs covered:** FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR19, FR34, FR35, FR38

### Epic 4: Scoring, Quality Signals & Session Completion
After completing all questions, the developer receives a 4-dimension comprehension score with verdict, can report problematic questions, and provide post-session feedback. Score posted as informational GitHub status check, private by default.
**FRs covered:** FR12, FR13, FR14, FR15, FR16, FR17, FR18

### Epic 5: Demo Experience & Landing Page
Visitors can experience the full Socratic challenge on a pre-loaded open-source PR without any authentication or API key, then convert to GitHub App installation via contextual CTA. Includes the marketing landing page.
**FRs covered:** FR28, FR29, FR30

### Epic 6: Billing & Subscriptions
The system distinguishes free public repos from paid private repos, enables subscription management via Lemon Squeezy checkout, and tracks per-seat usage per installation.
**FRs covered:** FR31, FR32, FR33

## Epic 1: GitHub App Installation & Identity

Admins can install the helPRs GitHub App on their org/repo, configure their BYOK Anthropic API key, and developers can authenticate via GitHub OAuth. Includes project scaffolding, core infrastructure, identity module, installation module, and admin UI.

### Story 1.1: Project Scaffolding & Deployment Infrastructure

As a **developer on the helPRs team**,
I want the monorepo initialized with backend, frontend, infrastructure, CI/CD pipelines, design token foundation, and production deployment config,
So that all future stories have a consistent development environment and automated deployment to build upon.

**Acceptance Criteria:**

**Given** a fresh clone of the repository
**When** I run `make dev`
**Then** Docker Compose starts 3 services (api, web, db) with hot reload on both backend (uvicorn --reload) and frontend (Vite HMR)

**Given** the backend service is running
**When** I visit the `/docs` endpoint
**Then** I see the FastAPI auto-generated OpenAPI documentation

**Given** the frontend service is running
**When** I visit the Vite dev server URL
**Then** I see a minimal React app with the helPRs design tokens applied (warm dark background `#201d1d`, Berkeley Mono / IBM Plex Mono font stack)

**Given** a push to any branch
**When** the GitHub Actions CI pipeline (`ci.yml`) runs
**Then** it executes lint (ruff + eslint), test (pytest + vitest), and build steps in sequence

**Given** a push to main
**When** the GitHub Actions deploy pipeline (`deploy.yml`) runs
**Then** it builds multi-stage Docker images (Dockerfile.api, Dockerfile.web), pushes them to the container registry, and triggers Coolify deployment

**Given** the production Docker images
**When** Coolify deploys them using `infra/coolify/docker-compose.prod.yml`
**Then** the api and web services start successfully with production configuration (no hot reload, production builds)

**Given** the Tailwind config
**When** I inspect the generated CSS
**Then** all design tokens from DESIGN.md are available as utilities — colors (primary, semantic, border), spacing (8px grid), border radius (4px/6px), and typography scale

**Given** the backend project
**When** I run `make lint` and `make test`
**Then** ruff checks pass and pytest discovers the test directory with a passing placeholder test

**Given** the monorepo structure
**When** I list the directory tree
**Then** it matches the architecture: `apps/api/src/helprs/`, `apps/web/src/`, `infra/docker/`, `infra/coolify/`, `docker-compose.yml`, `Makefile`, `.env.example`

### Story 1.2: Core Backend Infrastructure

As a **developer on the helPRs team**,
I want shared core infrastructure (database, config, middleware, logging, error handling) in place,
So that all backend modules can rely on consistent patterns for data access, security, and observability.

**Acceptance Criteria:**

**Given** the API service starts
**When** it connects to PostgreSQL
**Then** an async SQLAlchemy engine and session factory are initialized, and Alembic is configured with an empty initial migration

**Given** environment variables are set (or `.env` file exists)
**When** the application loads configuration
**Then** pydantic-settings validates all required values (DATABASE_URL, SECRET_KEY, GITHUB_APP_ID, etc.) and raises clear errors for missing values

**Given** any API request
**When** it originates from a non-helPRs domain
**Then** CORS middleware rejects it with appropriate headers

**Given** a domain exception is raised (e.g., `BYOKKeyInvalidError`)
**When** the global exception handler catches it
**Then** it returns a structured JSON response `{"error": "byok_key_invalid", "message": "...", "detail": null}` with the correct HTTP status code

**Given** any API request
**When** it is processed
**Then** structlog produces JSON-structured log entries with correlation IDs (request_id) and Sentry captures unhandled exceptions

**Given** the rate limiting middleware
**When** an IP exceeds the auth endpoint rate limit
**Then** subsequent requests receive 429 Too Many Requests responses

**Given** the admin panel
**When** an internal team member visits `/admin`
**Then** SQLAdmin renders model views (initially empty, models added by future stories)

### Story 1.3: GitHub OAuth & User Identity

As a **developer**,
I want to authenticate with my GitHub identity and receive a JWT,
So that I can access helPRs sessions without creating a separate account.

**Acceptance Criteria:**

**Given** an unauthenticated developer
**When** they visit `GET /api/v1/auth/github`
**Then** they are redirected to GitHub's OAuth authorization page with the correct client_id and scopes

**Given** a developer completes GitHub OAuth
**When** GitHub redirects to the callback URL with an authorization code
**Then** the system exchanges the code for a GitHub access token, creates or updates a `github_users` record, and issues a short-lived JWT (15 min) + refresh token in an httpOnly secure cookie

**Given** a valid JWT in the Authorization header
**When** a developer makes any API request
**Then** the `get_current_user` dependency extracts and validates the JWT, returning the current user

**Given** an expired JWT but valid refresh token cookie
**When** the developer calls `POST /api/v1/auth/refresh`
**Then** a new JWT is issued without requiring re-authentication

**Given** an invalid or expired refresh token
**When** the developer calls the refresh endpoint
**Then** they receive 401 Unauthorized and must re-authenticate via OAuth

**Given** the frontend React app
**When** a developer is redirected back from GitHub OAuth
**Then** the `OAuthCallback` component stores the JWT in the auth store (Zustand) and redirects to the intended destination

**Given** an unauthenticated user
**When** they attempt to access a protected route
**Then** the `ProtectedRoute` component redirects them to the GitHub OAuth flow

**Given** a developer's GitHub OAuth token
**When** the system stores it
**Then** it is stored securely with minimum required scopes (NFR11)

### Story 1.4: GitHub App Installation & Webhook Registration

As an **admin**,
I want to install the helPRs GitHub App on my organization or repository,
So that helPRs can receive PR webhook events and create comprehension sessions for my team.

**Acceptance Criteria:**

**Given** an admin visits the GitHub App installation page
**When** they authorize helPRs for their org (all or selected repos) or a specific repo
**Then** GitHub sends an `installation.created` webhook to helPRs

**Given** a valid `installation.created` webhook arrives
**When** the system verifies the HMAC SHA-256 signature against the webhook secret
**Then** it creates an `installations` record with the GitHub installation_id, account info, and repository scope

**Given** an invalid webhook signature
**When** the system receives any webhook
**Then** it rejects the payload with 401 and logs a security warning

**Given** an admin uninstalls the GitHub App
**When** GitHub sends an `installation.deleted` webhook
**Then** the system soft-deletes the installation record and associated configuration

**Given** a developer is authenticated
**When** they attempt to access installation settings
**Then** the system verifies they have admin permissions on the GitHub org/repo and returns 403 if not

**Given** an installation exists
**When** the system needs to interact with GitHub on behalf of that installation
**Then** it uses scoped installation access tokens (not app-level credentials) per NFR12

### Story 1.5: BYOK Configuration & Admin Settings UI

As an **admin**,
I want to configure my Anthropic API key, set bot suppression labels, and view my installation settings,
So that helPRs can use my key for LLM calls and I can control when helPRs activates.

**Acceptance Criteria:**

**Given** an admin is authenticated and has admin permissions
**When** they submit an Anthropic API key via `POST /api/v1/installations/{id}/byok`
**Then** the system validates the key against the Anthropic API, encrypts it with Fernet, and stores the ciphertext in `byok_configs`

**Given** an admin submits an invalid API key
**When** validation against Anthropic API fails
**Then** the system returns a clear error message ("API key validation failed — check your key and try again") without storing the key

**Given** an admin has configured a valid BYOK key
**When** they view their installation settings (`GET /api/v1/installations/{id}`)
**Then** they see: connected repos, key status (valid/configured date), and current suppression labels — the key value itself is never returned

**Given** an admin wants to configure bot suppression
**When** they update labels via `PUT /api/v1/installations/{id}/suppression-labels`
**Then** the system stores the labels (defaults: hotfix, urgent, trivial) and confirms the update

**Given** the frontend SetupView page
**When** an admin arrives after GitHub App installation redirect
**Then** they see a single primary task (API key input with paste field), optional suppression labels with defaults pre-filled, and a setup-complete summary when finished

**Given** the frontend SettingsView page
**When** an admin visits their installation settings
**Then** they can view current config, update their API key, and manage suppression labels with immediate validation feedback

**Given** a BYOK key stored in the database
**When** the system needs to decrypt it for LLM calls
**Then** Fernet decryption using the master key (from env var) returns the original API key

## Epic 2: Webhook Processing & Session Lifecycle

When a developer opens a PR, helPRs automatically creates a comprehension session and posts a PR comment with session links for both author and reviewer roles. Supports bot suppression via configured labels.

### Story 2.1: Webhook Reception & Event Dispatch

As a **system**,
I want to receive GitHub PR webhook events, verify their authenticity, persist them, and route them to the correct handler,
So that no PR event is lost and processing is reliable even if the server restarts.

**Acceptance Criteria:**

**Given** GitHub sends a `pull_request.opened` or `pull_request.synchronize` webhook
**When** the payload arrives at `POST /webhooks/github`
**Then** the system verifies the HMAC SHA-256 signature, persists the raw event to the database, returns 200 immediately, and dispatches processing to a BackgroundTask

**Given** the server crashes after returning 200 but before processing completes
**When** the server restarts
**Then** a startup job detects unprocessed events in the database and replays them

**Given** a webhook with an unhandled event type (e.g., `issues.opened`)
**When** the dispatcher routes the event
**Then** it logs the event type at info level and discards it without error

**Given** GitHub does not receive a 200 response within the timeout
**When** GitHub retries the webhook delivery
**Then** the system handles the duplicate event idempotently (no duplicate sessions created)

**Given** the webhook module
**When** processing any event
**Then** structlog entries include `installation_id` and `event_type` as correlation context

### Story 2.2: Session Creation & PR Comment Posting

As a **developer**,
I want helPRs to automatically create a comprehension session and post a PR comment with session links when I open a PR,
So that I can start a Socratic challenge directly from my pull request.

**Acceptance Criteria:**

**Given** a `pull_request.opened` event is dispatched
**When** the handler processes it
**Then** it creates a new session record in the `sessions` table with the PR metadata (repo, PR number, title, diff URL), status `pending`, and two role entries (author, reviewer)

**Given** a session is created
**When** the handler fetches the PR diff via the GitHub API
**Then** it uses the installation's scoped access token and stores the diff reference (not the code itself) in the session metadata

**Given** a session is ready
**When** the handler posts a PR comment via the GitHub API
**Then** the comment contains two session links (one for author, one for reviewer) in a concise format (2-3 lines max, warm tone) and completes within 10 seconds of the original webhook (NFR1)

**Given** a PR has labels matching the installation's suppression list (e.g., "hotfix")
**When** the webhook handler checks suppression rules
**Then** no session is created and no PR comment is posted

**Given** a `pull_request.synchronize` event (new push to existing PR)
**When** the handler processes it
**Then** it updates the existing session's diff reference (or creates a new session if none exists) without posting a duplicate comment

**Given** the GitHub API is temporarily unavailable
**When** the handler attempts to post a PR comment
**Then** it retries with exponential backoff (NFR23) and logs the failure — the session record is preserved regardless

## Epic 3: Socratic Comprehension Experience

A developer can engage in a full Socratic comprehension session — AI-generated questions streaming in real-time, answers with per-question feedback, code-linked diff navigation in a split-view interface. Questions adapt to role (author/reviewer) and PR size, with beyond-diff probing for depth.

### Story 3.1: Comprehension Domain Model & Session API

As a **developer**,
I want to load my session with its PR context and track my progress through questions and answers,
So that the system maintains my session state reliably across the entire Socratic challenge.

**Acceptance Criteria:**

**Given** the comprehension module domain layer
**When** the entities are defined
**Then** `Session`, `Question`, `Answer` aggregates exist with value objects `SessionRole` (author/reviewer), `SessionStatus` (pending/active/completed), and `Topic` — all as pure Python + Pydantic with no framework imports

**Given** an authenticated developer with access to the repository
**When** they call `GET /api/v1/sessions/{id}`
**Then** the system verifies repo access (FR26), returns session metadata (repo name, PR title, role, status, question count), and the diff content fetched in-memory from GitHub (never stored server-side per NFR13)

**Given** a developer without access to the session's repository
**When** they attempt to load the session
**Then** the system returns 403 Forbidden

**Given** the session repository infrastructure layer
**When** session data is persisted
**Then** only metadata is stored (scores, topics, timestamps, question hashes) — no verbatim questions, answers, or source code (FR35, NFR14)

**Given** the comprehension module structure
**When** inspecting the codebase
**Then** it follows full DDD layers: `domain/` (entities, value_objects, services, interfaces), `application/` (commands, queries, handlers), `infrastructure/` (models, repositories, agents), `presentation/` (routers, schemas, sse, dependencies)

**Given** the domain layer interfaces
**When** `SessionRepository` and `LLMProvider` ports are defined
**Then** they are abstract interfaces in `domain/interfaces.py` with concrete implementations in `infrastructure/` — the domain imports nothing external

### Story 3.2: Split-View Session UI & Diff Viewer

As a **developer**,
I want a split-view interface showing the chat on the left and my PR diff on the right,
So that I can read questions and reference my code changes simultaneously.

**Acceptance Criteria:**

**Given** a developer opens their session URL
**When** the session page loads
**Then** a split-view layout renders with the chat panel (~60% width) on the left and the diff panel (~40%) on the right, separated by a draggable resize handle (4px visual, 12px hit area)

**Given** the diff panel
**When** the PR diff is loaded
**Then** it displays a unified diff with syntax highlighting, line numbers on both sides, and file tabs (14px weight 500, active tab bold 700) for navigating between changed files

**Given** the resize handle
**When** a developer drags it or uses arrow keys
**Then** the panel widths adjust in real-time with the resize handle accessible via keyboard (UX-DR17)

**Given** a viewport width below 1100px
**When** the session page renders
**Then** the layout collapses to a tabbed interface (Chat / Diff toggle tabs)

**Given** a viewport width below 768px
**When** the session page renders
**Then** only the chat panel is shown with a subtle banner: "Open on desktop for the full experience with code view"

**Given** the session header
**When** it renders
**Then** it displays repo name (16px bold), PR title (16px regular), role badge (Author: accent blue / Reviewing: warning orange, 12px uppercase), progress indicator ("Question 0 of N", 14px gray with aria-live="polite"), and AI disclaimer (12px muted, FR19) — fixed at 48px height

**Given** chat messages in the chat panel
**When** the content exceeds the max width
**Then** messages are constrained to 720px max-width within the panel

**Given** the diff panel background
**When** rendered
**Then** it uses `#302c2c` (dark surface) to visually distinguish it from the chat panel (`#201d1d`)

### Story 3.3: Question Generation & SSE Streaming

As a **developer**,
I want the AI to generate Socratic questions from my PR diff and stream them to me in real-time,
So that I can begin thinking about my code immediately without waiting for the full response.

**Acceptance Criteria:**

**Given** a developer opens an active session
**When** they connect to `GET /api/v1/sessions/{id}/stream`
**Then** an SSE connection is established and the first question begins streaming within 3 seconds (NFR2)

**Given** the Pydantic AI question_agent
**When** it generates a question from the PR diff using the installation's BYOK key
**Then** the API call uses the user's key directly with zero-retention (FR34), and the question is streamed token-by-token as SSE events with type `question` containing `{"question_id", "text", "number", "total"}`

**Given** the frontend useSSE hook
**When** it receives SSE events
**Then** it parses event types (question, feedback, score, error), updates the Zustand session store, and reconnects with exponential backoff on connection loss (AR14)

**Given** the chat panel
**When** a question streams in
**Then** it renders as an AI message with markdown support, token-by-token animation, and "helPRs asks:" screen reader prefix (UX-DR18)

**Given** a user with `prefers-reduced-motion` enabled
**When** a question streams
**Then** the full question text appears at once instead of token-by-token (UX-DR3)

**Given** the first token of a streaming response
**When** it arrives from the LLM
**Then** the latency is under 1 second (NFR3)

**Given** the question references specific files in the diff
**When** it renders in the chat panel
**Then** the corresponding file tab in the diff panel is highlighted with accent blue (UX-DR6)

**Given** all AI-generated content (questions)
**When** they are displayed
**Then** they are labeled as AI-produced (FR38)

### Story 3.4: Answer Submission & Feedback with Code Links

As a **developer**,
I want to submit my answer and receive streaming feedback that links to specific code sections in my diff,
So that I can understand exactly where my comprehension gaps are.

**Acceptance Criteria:**

**Given** the chat input component
**When** it renders
**Then** it is fixed at the bottom with 48px minimum height (auto-expand), 16px padding, Enter to submit, Shift+Enter for newline (UX-DR4)

**Given** a developer types an answer and presses Enter
**When** the answer is submitted
**Then** the answer appears immediately in the chat as a user message (optimistic UI, UX-DR20) with `#302c2c` background, and the input is disabled while feedback generates

**Given** an answer is submitted to `POST /api/v1/sessions/{id}/answers`
**When** the Pydantic AI feedback_agent evaluates it
**Then** feedback streams via SSE as type `feedback` with `{"question_id", "score", "gaps", "code_refs"}`, beginning with acknowledgment of what was right before identifying gaps (NFR4: < 5s)

**Given** feedback contains code references (e.g., `retry.ts:47`)
**When** they render in the chat
**Then** they appear as clickable links (accent blue `#007aff`, 16px weight 500) that, on click, scroll the diff panel to the referenced lines and highlight them with `rgba(0, 122, 255, 0.15)` overlay (UX-DR6)

**Given** a developer hovers over a code link
**When** the hover event fires
**Then** the diff panel subtly highlights the target lines without scrolling (hover preview, UX-DR6)

**Given** feedback finishes streaming
**When** the next question is ready
**Then** a 16px gap separates feedback from the next question, and the next question begins streaming automatically — no "Next" button needed

**Given** the LLM times out during feedback generation
**When** 5 seconds elapse with no response
**Then** the UI shows "Taking a moment to think..." with auto-retry, then "Connection issue. Your progress is saved — try refreshing" if persistent (UX-DR19)

**Given** the developer loses internet connection
**When** they submit an answer
**Then** the chat shows "Reconnecting..." and queues the answer locally until connection restores (UX-DR19)

**Given** the LLM produces an empty response
**When** the system detects it
**Then** it skips to the next question with a note: "Skipped a question that didn't generate properly" (UX-DR19)

### Story 3.5: Role Adaptation, Beyond-Diff & Large PR Handling

As a **developer**,
I want questions tailored to my role (author or reviewer), probing beyond the visible diff, and intelligently scoped for large PRs,
So that the session is always relevant, deep, and proportional to the PR's complexity.

**Acceptance Criteria:**

**Given** a developer opens an author session
**When** the question_agent generates questions
**Then** questions probe decisions, tradeoffs, edge cases, and architectural choices — "Why did you choose this approach?" / "What happens if this fails?" (FR7)

**Given** a developer opens a reviewer session
**When** the question_agent generates questions
**Then** questions probe understanding of what the changes do and their impact — "What user-facing behavior changes?" / "How does this affect the existing API contract?" (FR7)

**Given** a PR of any size
**When** the question_agent analyzes the diff
**Then** it generates questions that go beyond the diff content — probing callers, consumers, architectural decisions, and system-level impact of the changes (FR10)

**Given** a small PR (< 100 lines changed)
**When** the session is created
**Then** the question count is 3-5 questions (FR6)

**Given** a medium PR (100-500 lines changed)
**When** the session is created
**Then** the question count is 5-7 questions (FR6)

**Given** a large PR (> 500 lines changed)
**When** the session is created
**Then** the question count is 7-10 questions (FR6)

**Given** a PR with 2000+ lines changed across many files
**When** the question_agent processes the diff
**Then** it selects files with the highest line-change count for detailed analysis, provides stats on all changed files, and generates questions focused on the most impactful changes (FR11)

**Given** the question generation prompt
**When** it is configured for the session
**Then** it adapts the challenge-me plugin's SKILL.md foundation prompt (~220 lines) for the web context, incorporating role, PR metadata, and diff content

## Epic 4: Scoring, Quality Signals & Session Completion

After completing all questions, the developer receives a 4-dimension comprehension score with verdict, can report problematic questions, and provide post-session feedback. Score posted as informational GitHub status check, private by default.

### Story 4.1: Comprehension Scoring & Score Card UI

As a **developer**,
I want to receive a comprehension score across four dimensions with a verdict after completing all questions,
So that I understand how well I know my code and where to deepen my understanding.

**Acceptance Criteria:**

**Given** a developer has answered all questions in their session
**When** the Pydantic AI scoring_agent evaluates the complete session
**Then** it produces scores across four dimensions (Depth, Accuracy, Completeness, Insight) on a 0-10 scale and a verdict (Exceptional 9-10, Strong 7-8, Adequate 5-6, Weak 3-4, Insufficient 0-2) within 10 seconds (NFR5)

**Given** the scoring is complete
**When** the score is streamed via SSE as type `score`
**Then** a score card renders inline in the chat as the conversation's natural conclusion — no redirect to a separate results page

**Given** the score card component
**When** it renders
**Then** it displays 4 horizontal dimension bars (Depth: accent blue, Accuracy: success green, Completeness: warning orange, Insight: `#ff3b30` warm accent), a verdict badge with color mapping (Exceptional: green, Strong: blue, Adequate: gray, Weak/Insufficient: warning orange — never danger red), a gap summary labeled "Areas to deepen", with 24px padding (UX-DR8)

**Given** the score card
**When** a screen reader reads it
**Then** all dimension values and the verdict have descriptive ARIA labels (UX-DR18)

**Given** any session score
**When** it is stored
**Then** visibility is private by default — only the session participant can view it (FR16)

**Given** a developer views their completed session
**When** they access `GET /api/v1/sessions/{id}`
**Then** the response includes the full score breakdown, verdict, and gap summary (FR15)

**Given** all AI-generated content (scores, feedback)
**When** they are displayed
**Then** they are labeled as AI-produced (FR38)

### Story 4.2: GitHub Status Check, Question Reporting & Post-Session Feedback

As a **developer**,
I want helPRs to post my score as an informational status check on my PR, report problematic questions, and provide session feedback,
So that my team sees comprehension signals and question quality improves over time.

**Acceptance Criteria:**

**Given** a session is scored
**When** the system posts a GitHub status check
**Then** it is informational (never merge-blocking), shows the verdict and overall score, and uses the installation's scoped access token (FR14)

**Given** an AI question in the chat
**When** a developer clicks the report flag icon (`#6e6e73` muted, small)
**Then** a minimal "Why is this question problematic?" selector opens inline without interrupting the conversation flow (UX-DR9)

**Given** a developer selects a report reason
**When** the report is submitted via `POST /api/v1/sessions/{id}/questions/{qid}/report`
**Then** the report is persisted with the question hash, reason, and session metadata — the developer sees confirmation and the flow continues

**Given** the score card has rendered
**When** the post-session feedback UI appears below it
**Then** it shows thumbs up/down buttons and an optional comment field, not intrusive (UX-DR10)

**Given** a developer submits post-session feedback
**When** they click thumbs up/down and optionally add a comment
**Then** the feedback is persisted via `POST /api/v1/sessions/{id}/feedback` with the rating and comment

**Given** the report button on each question
**When** it is focused via keyboard
**Then** it is reachable via Tab and activated with Enter (UX-DR17)

## Epic 5: Demo Experience & Landing Page

Visitors can experience the full Socratic challenge on a pre-loaded open-source PR without any authentication or API key, then convert to GitHub App installation via contextual CTA. Includes the marketing landing page.

### Story 5.1: Demo Session & Pre-loaded Experience

As a **visitor**,
I want to experience a full Socratic challenge session without signing up or configuring anything,
So that I can understand the value of helPRs before installing it.

**Acceptance Criteria:**

**Given** a visitor clicks "Try the demo" on the landing page
**When** the demo session loads
**Then** a pre-loaded session opens on a real, recognizable open-source PR with the full split-view interface, no authentication required, in under 2 seconds (NFR6)

**Given** the demo session
**When** it runs
**Then** it uses a shorter format (2-3 questions instead of 3-10) to respect the visitor's exploratory mindset, while reproducing the complete flow: questions, answers, feedback with code links, and scoring (FR29)

**Given** the demo session
**When** questions are generated
**Then** they use helPRs' own API key (not BYOK) since the visitor has no installation

**Given** the demo session completes
**When** the score card appears
**Then** a contextual CTA renders below the score: "That was a demo. Install helPRs on your repo to challenge yourself on your own PRs" with a button linking to the GitHub App installation flow (FR30)

**Given** the demo session
**When** it is accessed
**Then** no session data is persisted beyond basic anonymous analytics (page views, demo completion rate)

**Given** the demo diff content
**When** the demo is set up
**Then** a seed script or fixture provides the pre-loaded PR data (diff, metadata) from a well-known open-source project

### Story 5.2: Landing Page & Install Conversion

As a **visitor**,
I want to understand what helPRs does and install it on my repository,
So that I can start using Socratic comprehension challenges on my team's PRs.

**Acceptance Criteria:**

**Given** a visitor navigates to helprs.dev
**When** the landing page loads
**Then** it displays a hero section with value prop and prominent "Try the demo" CTA, following the OpenCode-inspired terminal-native dark aesthetic (`#201d1d` background, Berkeley Mono typography)

**Given** the landing page
**When** the visitor scrolls
**Then** they see: "How it works" section (3-step flow), pricing section (free for public repos, team plan for private), and social proof area

**Given** the "Install GitHub App" CTA
**When** a visitor clicks it
**Then** they are redirected to the GitHub App installation page to authorize helPRs on their org/repo

**Given** the landing page
**When** it loads on a mobile device
**Then** it is fully responsive with appropriate typography scaling (38px → 28px → 24px headings) and stacked layout

**Given** the landing page initial load
**When** measured on a 4G connection
**Then** time to interactive is under 3 seconds (NFR7)

## Epic 6: Billing & Subscriptions

The system distinguishes free public repos from paid private repos, enables subscription management via Lemon Squeezy checkout, and tracks per-seat usage per installation.

### Story 6.1: Billing Model & Lemon Squeezy Integration

As an **admin**,
I want helPRs to handle billing for private repo usage and track seat consumption,
So that my team can use helPRs on private repositories with transparent billing.

**Acceptance Criteria:**

**Given** an installation with connected repositories
**When** the system evaluates billing status
**Then** it distinguishes public repos (free, unlimited) from private repos (paid, requires active subscription) using the GitHub API repo visibility field (FR31)

**Given** an admin wants to use helPRs on private repos
**When** they access billing via `GET /api/v1/billing/{installation_id}`
**Then** the system provides a Lemon Squeezy checkout URL for the team plan (FR32)

**Given** a successful payment
**When** Lemon Squeezy sends a webhook to `POST /webhooks/lemonsqueezy`
**Then** the system creates a `subscriptions` record linked to the installation with plan details, start date, and billing period

**Given** an active subscription
**When** the billing period is active
**Then** the system tracks seat usage: each GitHub user who starts at least one session counts as one seat (FR33)

**Given** the seat tracking
**When** an admin views their billing status
**Then** they see current seat count, subscription status, and next billing date

**Given** a subscription expires or is cancelled
**When** a developer on a private repo opens a PR
**Then** helPRs posts the PR comment but the session link shows a message directing the admin to renew the subscription

**Given** the Lemon Squeezy integration
**When** handling payments
**Then** Lemon Squeezy acts as merchant of record, handling VAT/tax compliance (AR20)
