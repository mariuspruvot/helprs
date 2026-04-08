---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-04-08'
inputDocuments:
  - product-brief-helprs.md
  - product-brief-helprs-distillate.md
  - prd.md
  - prd-validation-report.md
  - research/domain-ai-pr-review-github-apps-research-2026-04-08.md
workflowType: 'architecture'
project_name: 'helprs'
user_name: 'Marius.pruvot'
date: '2026-04-08'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
38 FRs organized in 9 categories covering the complete product lifecycle:
- Session Lifecycle (FR1-5): Webhook reception, PR comment posting, bot suppression, GitHub OAuth auth, split-view UI
- Socratic Challenge (FR6-11): Question generation from diffs, role-based question types (author vs reviewer), real-time streaming delivery, per-answer feedback with code links, beyond-diff probing, large PR handling (2000+ lines)
- Scoring & Feedback (FR12-16): 4-dimension scoring (Depth, Accuracy, Completeness, Insight), verdict system, GitHub status checks (informational only), private-by-default scores
- Question Quality (FR17-19): Report button, post-session feedback, AI-generated disclaimer
- Installation & Configuration (FR20-24): GitHub App install (org/repo), BYOK API key config with validation, suppression labels, settings view
- Authentication & Authorization (FR25-27): GitHub-native identity, repo access verification, admin role restriction
- Demo Experience (FR28-30): Pre-loaded session without auth, full Socratic flow, conversion CTA
- Billing (FR31-33): Public/private repo distinction, payment flow, per-seat tracking
- Data & Privacy (FR34-38): BYOK zero-retention, metadata-only storage, key encryption at rest, webhook signature verification, AI content labeling

**Non-Functional Requirements:**
- Performance: Webhook processing <10s, first question <3s, streaming first token <1s, feedback <5s, score + status check <10s, demo load <2s, cold start <3s on 4G
- Security: TLS 1.2+, BYOK keys encrypted at rest, webhook cryptographic verification, scoped installation tokens, zero source code storage, metadata-only session storage, rate limiting, CORS
- Scalability: 100+ concurrent installations, independent horizontal scaling (webhooks vs chat), tenant isolation, <500ms p95 at 1M sessions
- Reliability: 99.5% uptime, graceful degradation (Anthropic API: error + retry, GitHub API: queue + backoff), persistent session state

**Scale & Complexity:**
- Primary domain: Full-stack web (SPA frontend + API backend + async webhook processing)
- Complexity level: Medium-High
- Estimated architectural components: 8-12 (webhook processor, session manager, LLM orchestrator, chat server, auth service, config/admin, demo service, billing tracker, frontend SPA)

### Technical Constraints & Dependencies

- BYOK model: helPRs never proxies LLM calls through own keys. User's Anthropic API key used directly. Zero code retention server-side
- GitHub App: All GitHub interactions via installation access tokens (scoped per install). Webhook payload limit 25MB. API version 2026-03-10
- Single LLM provider (Claude API) for MVP. Architecture should accommodate multi-LLM future
- 2-person team constraint: Architecture must be simple enough for 2 developers to build, deploy, and operate
- No codebase indexing/RAG in MVP: Questions generated from diff + immediate file context only
- challenge-me plugin's run SKILL.md (~220 lines) is the foundation prompt to adapt for web context
- Design system: OpenCode AI inspired (Berkeley Mono, warm dark theme, terminal-like chat)

### Cross-Cutting Concerns Identified

- **Security**: BYOK key lifecycle (storage, encryption, validation, rotation), webhook HMAC verification, OAuth token management, zero code retention enforcement, CORS policy
- **Observability**: Session analytics data collection from day 1 (scores, topics, timestamps, question hashes), question report tracking, feedback collection -- even without UI to display it
- **Compliance**: GDPR privacy policy + cookie consent, EU AI Act Art. 50 transparency labeling on all AI content, zero-retention on LLM calls
- **Rate Limiting**: 50 sessions/day per installation, auth endpoint protection, abuse prevention
- **Error Handling**: Graceful degradation for external dependencies (Anthropic API, GitHub API), session state persistence across failures
- **Multi-tenancy**: Installation-scoped data isolation, cross-installation user identity (GitHub-native)

## Starter Template Evaluation

### Primary Technology Domain

Full-stack web (Python API backend + React SPA frontend) in a polyglot monorepo.

### Technology Stack (Verified Versions)

**Backend:**
- Python 3.12+ (recommended for FastAPI performance)
- FastAPI 0.135.3 -- async-first, native SSE, OpenAPI auto-generation
- SQLAlchemy 2.0.49 ORM -- async support, mature ecosystem
- Alembic -- database migrations
- Pydantic v2 -- validation, settings, serialization (bundled with FastAPI)
- Pydantic AI 1.77.0 -- LLM agent framework with structured outputs, streaming, model-agnostic. Replaces custom LLM adapter
- SQLAdmin 0.24.0 -- internal admin panel for helPRs team

**Astral Toolchain:**
- uv -- package management, virtual environments, Python version management
- ruff 0.15+ -- linting + formatting (replaces flake8, black, isort, pyupgrade in one tool)

**Frontend:**
- React 19 + TypeScript
- Vite 8.0.7 -- Rolldown bundler (10-30x faster builds)
- React Router 7.14.0 -- routing
- Zustand 5.0.12 -- global state management (session state, UI state)
- TanStack Query 5.96.2 -- server state, caching, mutations
- Custom SSE hook -- real-time chat streaming
- Tailwind CSS -- utility-first styling (OpenCode-inspired dark theme)

**Infrastructure:**
- PostgreSQL -- primary database
- Docker -- containerized services (one Dockerfile per service)
- Docker Compose -- local development orchestration
- Coolify -- deployment on Kimsufi dedicated server

**Integrations:**
- GitHub App (webhooks + REST API + OAuth)
- Anthropic Claude API (BYOK, via user's key)
- Lemon Squeezy (payment, merchant of record -- handles VAT/tax)

### Starter Options Considered

| Option | Verdict | Rationale |
|--------|---------|-----------|
| Tiangolo full-stack-fastapi-template | Rejected | Imposes Next.js frontend, structure doesn't align with DDD/clean architecture goals |
| Community clean-architecture templates | Rejected | Small maintainership, would need heavy customization anyway |
| Turborepo monorepo | Rejected | JS/TS-centric, requires artificial package.json wrappers for Python projects. Overhead not justified for 2-person team |
| **Composable custom setup** | **Selected** | Maximum alignment with DDD/clean architecture. Senior Python dev can scaffold efficiently. Architecture document defines the structure |

### Selected Approach: Composable Custom Setup

**Rationale:**
- No existing starter aligns with clean architecture/DDD for a Python + React polyglot monorepo
- Custom setup avoids "starter debt" -- removing and replacing opinionated choices
- Architecture document becomes the canonical reference for project structure
- 2-person team benefits from understanding every layer, not inheriting a black box

**Initialization Commands:**

```bash
# Create monorepo structure
mkdir -p helprs/{apps/api,apps/web,infra}

# Backend setup
cd helprs/apps/api
uv init --python 3.12
uv add fastapi[standard] sqlalchemy[asyncio] alembic pydantic-settings asyncpg sqladmin python-jose cryptography httpx pydantic-ai
uv add --dev ruff pytest pytest-asyncio httpx

# Frontend setup
cd ../web
npm create vite@latest . -- --template react-swc-ts
npm install zustand @tanstack/react-query react-router tailwindcss @tailwindcss/vite

# Infrastructure
cd ../../infra
# Docker Compose, Dockerfiles, Coolify config
```

**Monorepo Structure:**

```
helprs/
├── apps/
│   ├── api/              # FastAPI backend
│   │   ├── src/
│   │   │   └── helprs/   # Python package (clean architecture layers defined in step 4)
│   │   ├── tests/
│   │   ├── alembic/
│   │   └── pyproject.toml
│   └── web/              # React SPA
│       ├── src/
│       ├── public/
│       └── package.json
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   └── Dockerfile.web
│   └── coolify/
├── docker-compose.yml     # Local dev orchestration
├── Makefile               # Cross-project commands
└── README.md
```

**Architectural Decisions Provided by This Setup:**

**Language & Runtime:** Python 3.12+ (backend), TypeScript strict mode (frontend)

**Styling Solution:** Tailwind CSS with custom design tokens (OpenCode AI dark theme)

**Build Tooling:** Vite 8 + Rolldown (frontend), uv (backend), Docker multi-stage builds (production)

**Testing Framework:** pytest + pytest-asyncio + httpx (backend), Vitest (frontend)

**Code Organization:** Clean architecture layers (defined in architecture decisions step), feature-based frontend structure

**Development Experience:** Docker Compose for local stack, hot reload on both frontend (Vite HMR) and backend (uvicorn --reload), shared OpenAPI types generation

**Type Sharing Strategy:** FastAPI auto-generates OpenAPI spec. openapi-typescript generates TypeScript types from that spec. Zero manual type duplication between backend and frontend.

**Note:** Project initialization using these commands should be the first implementation story.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Data modeling approach (DDD hybrid)
- Session state persistence
- Authentication flow
- BYOK encryption
- Background task processing

**Important Decisions (Shape Architecture):**
- Rate limiting strategy
- Error handling patterns
- Frontend component structure
- Logging approach
- CI/CD pipeline

**Deferred Decisions (Post-MVP):**
- Caching layer (Redis) -- add only if PostgreSQL bottleneck measured
- Message queue (arq/Celery) -- add only if BackgroundTasks reliability insufficient
- CDN for frontend static assets
- Multi-LLM provider support -- Pydantic AI is model-agnostic, switching is a config change (`'anthropic:...'` → `'openai:...'`)

### Data Architecture

**Session State Persistence: PostgreSQL JSONB**
- Rationale: Single data store, survives server restarts (NFR requirement), supports analytical queries on session metadata. Session duration is 10-15 min with low write frequency (one per answer submission). No need for Redis in MVP
- Affects: comprehension module, infrastructure layer

**Caching: None for MVP**
- Rationale: Data is either in DB (sessions, config) or ephemeral in-memory (GitHub diffs during request). No hot-path data that benefits from a cache layer. Add Redis only if measured bottleneck
- Affects: infrastructure decisions in phase 2

**Data Modeling: DDD Hybrid (Full DDD for Core, Flat for Supporting)**
- Rationale: Only the comprehension module (sessions, questions, scoring, LLM orchestration) has enough complexity to warrant full DDD layers (domain/application/infrastructure/presentation). Supporting modules (installation, identity, billing) are thin CRUD -- flat structure (models.py, service.py, router.py, schemas.py). Reduces ~70 files to ~35 while preserving clean namespacing
- Rule: "Start flat. Promote to full DDD layers when complexity earns it"

**Backend Project Structure:**

```
apps/api/src/helprs/
├── core/                          # Shared cross-cutting concerns
│   ├── config.py                  # pydantic-settings (env, secrets)
│   ├── database.py                # Async SQLAlchemy engine + session factory
│   ├── security.py                # Encryption utils, HMAC helpers
│   ├── middleware.py              # CORS, rate limiting, request logging
│   ├── exceptions.py              # Base exception hierarchy
│   └── dependencies.py            # Shared FastAPI dependencies (db session, current user)
│
├── modules/
│   ├── comprehension/             # === CORE DOMAIN (Full DDD) ===
│   │   ├── domain/
│   │   │   ├── entities.py        # Session, Question, Answer, Score aggregates
│   │   │   ├── value_objects.py   # SessionRole, Verdict, ScoreDimension, Topic
│   │   │   ├── services.py        # ScoringService, QuestionSelectionService
│   │   │   └── interfaces.py      # Ports: SessionRepository, LLMProvider
│   │   ├── application/
│   │   │   ├── commands.py        # StartSession, SubmitAnswer, ReportQuestion
│   │   │   ├── queries.py         # GetSession, GetSessionResult
│   │   │   └── handlers.py        # Use case handlers (orchestration)
│   │   ├── infrastructure/
│   │   │   ├── models.py          # SQLAlchemy ORM models
│   │   │   ├── repositories.py    # SessionRepository implementation
│   │   │   └── agents.py          # Pydantic AI agents (question, feedback, scoring)
│   │   └── presentation/
│   │       ├── routers.py         # REST endpoints (/sessions/*)
│   │       ├── schemas.py         # Pydantic request/response DTOs
│   │       ├── sse.py             # SSE streaming endpoint
│   │       └── dependencies.py    # Module-specific DI
│   │
│   ├── installation/              # === SUPPORTING (Flat) ===
│   │   ├── models.py              # Installation, BYOKConfig SQLAlchemy models
│   │   ├── service.py             # CRUD + BYOK validation logic
│   │   ├── router.py              # /installations/* endpoints
│   │   └── schemas.py             # Pydantic DTOs
│   │
│   ├── identity/                  # === GENERIC SUBDOMAIN (Flat) ===
│   │   ├── models.py              # GitHubUser SQLAlchemy model
│   │   ├── service.py             # OAuth flow, token management
│   │   ├── router.py              # /auth/* endpoints
│   │   └── schemas.py
│   │
│   ├── billing/                   # === SUPPORTING (Flat) ===
│   │   ├── models.py              # Subscription, SeatUsage models
│   │   ├── service.py             # Lemon Squeezy integration logic
│   │   ├── router.py              # /billing/* + webhook endpoint
│   │   └── schemas.py
│   │
│   └── webhook/                   # === INBOUND ADAPTER ===
│       ├── router.py              # POST /webhooks/github
│       ├── verification.py        # HMAC signature verification
│       ├── dispatcher.py          # Event type -> handler routing
│       └── handlers.py            # PR event handlers (trigger session creation)
│
├── admin/                         # SQLAdmin views for internal team
│   └── views.py
│
└── main.py                        # App factory, router composition, lifespan
```

**Dependency Rule:** `presentation → application → domain ← infrastructure`. Domain imports nothing external (pure Python + Pydantic). Core is importable by all except domain.

**Inter-Context Communication:** Bounded contexts communicate via application services, not cross-domain imports. Example: `webhook.handlers` calls `comprehension.application.handlers.StartSessionHandler`. The comprehension module consumes installation config via a port (`InstallationConfigProvider`) implemented in infrastructure.

### Authentication & Security

**Authentication: JWT + Refresh Token**
- Flow: GitHub OAuth → helPRs issues short-lived JWT (15 min) + refresh token in httpOnly cookie
- Rationale: Stateless for SPA + API pattern, no server-side session store, compatible with multi-tab usage. httpOnly cookie protects refresh token from XSS
- Affects: identity module, core/dependencies.py (current_user extraction)

**BYOK Key Encryption: Fernet**
- Implementation: Python `cryptography` library Fernet symmetric encryption
- Master key: environment variable, rotatable
- Rationale: Simple, proven, sufficient for MVP. No external vault needed
- Affects: installation module, core/security.py

**Webhook Verification: HMAC SHA-256**
- Implementation: GitHub-standard webhook signature verification
- Location: webhook/verification.py middleware
- Rationale: Required by GitHub, no alternative

### API & Communication Patterns

**Background Task Processing: FastAPI BackgroundTasks + DB Persistence**
- Flow: Webhook arrives → verify HMAC → persist event to DB → return 200 → process in BackgroundTasks
- Reliability: If server crashes after 200, event is in DB for recovery. Startup job replays unprocessed events
- Rationale: No Redis/Celery for MVP. GitHub retries webhooks that don't receive 200. DB persistence covers the post-200 crash window
- Migration path: Replace with arq (async Redis queue) if volume demands it
- Affects: webhook module, comprehension application layer

**Rate Limiting: slowapi**
- Two levels: per-installation (50 sessions/day), per-IP (brute-force protection on auth endpoints)
- Implementation: slowapi middleware wrapping the limits library
- Affects: core/middleware.py

**Error Handling: Domain Exceptions → HTTP Mapping**
- Pattern: Domain-specific exceptions (SessionNotFoundError, BYOKKeyInvalidError) inherit from base DomainError with http_status and error code
- Global exception handler maps DomainError subclasses to structured JSON responses
- Affects: core/exceptions.py, all modules

### Frontend Architecture

**Component Structure: Feature-Based**

```
apps/web/src/
├── features/
│   ├── session/            # Chat UI, split view, SSE hook
│   ├── demo/               # Demo session (no auth)
│   ├── auth/               # OAuth callback, token management
│   ├── installation/       # Admin config pages
│   └── landing/            # Homepage, CTA
├── shared/
│   ├── components/         # Buttons, inputs, layout primitives
│   ├── hooks/              # useSSE, useAuth, useApi
│   ├── api/                # TanStack Query + generated OpenAPI types
│   └── theme/              # Design tokens, Tailwind config
└── app.tsx                 # Router, providers, layout
```

**SSE Streaming: Custom useSSE Hook**
- Reconnection with exponential backoff
- Event type parsing (question, feedback, score, error)
- Zustand integration for session chat state
- Affects: session feature, shared/hooks

### Infrastructure & Deployment

**CI/CD: GitHub Actions**
- Pipeline: lint (ruff + eslint) → test (pytest + vitest) → build Docker images → push to registry
- Rationale: Natural for a GitHub App project. Free tier sufficient for MVP

**Docker Compose (Local Dev): 3 Services**
- api: FastAPI + uvicorn (hot reload)
- web: Vite dev server (HMR)
- db: PostgreSQL 16

**Logging: structlog**
- JSON structured logging with correlation IDs (session_id, installation_id)
- Rationale: Essential for debugging multi-turn LLM sessions across async tasks

**Error Tracking: Sentry**
- Free tier (5K events/month), sufficient for MVP
- Captures unhandled exceptions in both API and background tasks

### Decision Impact Analysis

**Implementation Sequence:**
1. Project scaffolding (monorepo structure, Docker Compose, CI)
2. Core infrastructure (database, config, auth middleware)
3. Identity module (GitHub OAuth flow)
4. Installation module (GitHub App install, BYOK config)
5. Webhook module (GitHub event reception + dispatch)
6. Comprehension module (the core domain -- sessions, LLM, scoring, SSE)
7. Frontend (auth flow → session UI → demo → landing)
8. Billing module (Lemon Squeezy integration)

**Cross-Component Dependencies:**
- Comprehension depends on Installation (BYOK key to call Claude API) and Identity (session owner)
- Webhook depends on Installation (suppression rules) and Comprehension (session creation)
- Billing depends on Installation (subscription scope) and Identity (seat counting)
- Frontend depends on all backend API endpoints being available

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Database Naming (PostgreSQL + SQLAlchemy):**
- Tables: `snake_case`, plural → `sessions`, `installations`, `github_users`
- Columns: `snake_case` → `created_at`, `installation_id`, `byok_key_encrypted`
- Foreign keys: `{singular_table}_id` → `installation_id`, `user_id`
- Indexes: `ix_{table}_{columns}` → `ix_sessions_installation_id`
- Constraints: `uq_{table}_{columns}`, `ck_{table}_{constraint}`

**API Naming (FastAPI):**
- Endpoints: `snake_case`, plural, module-prefixed → `/api/v1/sessions`, `/api/v1/installations`
- Query params: `snake_case` → `?installation_id=xxx`
- JSON fields: `snake_case` (Pydantic default) → `{"session_id": "...", "created_at": "..."}`
- No envelope wrapper → return data directly. Pagination: `{"items": [...], "total": 42, "page": 1, "page_size": 20}`

**Python Code:**
- Files: `snake_case.py`
- Classes: `PascalCase` → `SessionRepository`, `StartSessionHandler`
- Functions/methods: `snake_case` → `start_session()`, `validate_byok_key()`
- Constants: `UPPER_SNAKE_CASE` → `MAX_SESSIONS_PER_DAY`

**TypeScript/React Code:**
- Component files: `PascalCase.tsx` → `ChatMessage.tsx`, `SplitView.tsx`
- Utility files: `camelCase.ts` → `useSSE.ts`, `apiClient.ts`
- Components: `PascalCase` → `<ChatMessage />`
- Functions/hooks: `camelCase` → `useSessionStore()`, `submitAnswer()`
- Types/interfaces: `PascalCase` → `SessionResponse`, `QuestionEvent`

### Structure Patterns

**Tests:**
- Backend: `apps/api/tests/` mirroring `src/` structure → `tests/modules/comprehension/test_handlers.py`
- Frontend: co-located → `features/session/ChatView.test.tsx`

**Imports:**
- Backend: always absolute from package → `from helprs.modules.comprehension.domain.entities import Session`
- Frontend: `@/` alias for `src/` → `import { useSSE } from '@/shared/hooks/useSSE'`

### Format Patterns

**API Responses:**
```
# Success: direct data
GET /api/v1/sessions/abc → {"id": "abc", "role": "author", "status": "in_progress", ...}

# Paginated list
GET /api/v1/sessions → {"items": [...], "total": 42, "page": 1, "page_size": 20}

# Error: uniform structure
4xx/5xx → {"error": "session_not_found", "message": "Session abc does not exist", "detail": null}
```

**Dates:** ISO 8601 UTC everywhere → `"2026-04-08T14:30:00Z"`

**IDs:** UUIDs v4 as strings for public entities (sessions, installations). Integer auto-increment for internal-only FK references.

### Communication Patterns

**SSE Event Types:**
```
event: question
data: {"question_id": "q1", "text": "...", "number": 1, "total": 5}

event: feedback
data: {"question_id": "q1", "score": 7, "gaps": [...], "code_refs": [...]}

event: score
data: {"depth": 7, "accuracy": 8, "completeness": 6, "insight": 5, "verdict": "strong"}

event: error
data: {"error": "llm_unavailable", "message": "...", "retryable": true}
```

**Zustand Stores:** One store per feature → `useSessionStore`, `useAuthStore`. No monolithic global store.

### Process Patterns

**Error Handling (Frontend):**
- TanStack Query `onError` for API errors
- React Error Boundaries per feature (not a single global one)
- Toast notifications for user-facing errors
- console.error + Sentry for developer errors

**Loading States:** Managed by TanStack Query (`isLoading`, `isFetching`). No manual `loading` booleans in Zustand.

### Enforcement Guidelines

**All AI Agents MUST:**
1. Follow naming conventions above without exception
2. Place code in the correct module/layer per the defined structure
3. Write tests alongside code (not separately)
4. Use OpenAPI-generated types -- never manually duplicate types between backend and frontend
5. Log with structlog including `session_id`/`installation_id` in context
6. Map domain exceptions to HTTP responses via the global exception handler
7. Use absolute imports (backend) and `@/` alias imports (frontend)
8. Return ISO 8601 UTC dates in all API responses
9. Use UUIDs for public-facing entity IDs

**Anti-Patterns to Avoid:**
- Importing domain layer code from infrastructure or presentation layers
- Cross-module domain imports (use application service ports instead)
- Manual loading state management when TanStack Query handles it
- Storing sensitive data (BYOK keys, OAuth tokens) in frontend state
- Returning camelCase JSON from the API (Pydantic snake_case is the standard)
- Creating wrapper/envelope response formats ({data: ..., meta: ...})

## Project Structure & Boundaries

### Complete Project Directory Structure

```
helprs/
├── .github/
│   └── workflows/
│       ├── ci.yml                     # Lint + test + build on PR
│       └── deploy.yml                 # Build Docker + push to registry on main
├── apps/
│   ├── api/
│   │   ├── src/
│   │   │   └── helprs/
│   │   │       ├── __init__.py
│   │   │       ├── main.py                    # App factory, router composition, lifespan events
│   │   │       ├── core/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── config.py              # pydantic-settings: env vars, secrets, feature flags
│   │   │       │   ├── database.py            # Async engine, session factory, Base model
│   │   │       │   ├── security.py            # Fernet encryption, HMAC helpers, JWT utils
│   │   │       │   ├── middleware.py           # CORS, rate limiting (slowapi), request logging
│   │   │       │   ├── exceptions.py          # DomainError base, HTTP exception handler
│   │   │       │   └── dependencies.py        # get_db_session, get_current_user, get_installation
│   │   │       ├── modules/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── comprehension/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── domain/
│   │   │       │   │   │   ├── __init__.py
│   │   │       │   │   │   ├── entities.py        # Session, Question, Answer, Score
│   │   │       │   │   │   ├── value_objects.py   # SessionRole, Verdict, ScoreDimension, Topic
│   │   │       │   │   │   ├── services.py        # ScoringService, QuestionSelectionService
│   │   │       │   │   │   └── interfaces.py      # SessionRepository, LLMProvider ports
│   │   │       │   │   ├── application/
│   │   │       │   │   │   ├── __init__.py
│   │   │       │   │   │   ├── commands.py        # StartSession, SubmitAnswer, ReportQuestion
│   │   │       │   │   │   ├── queries.py         # GetSession, GetSessionResult
│   │   │       │   │   │   └── handlers.py        # Use case orchestration
│   │   │       │   │   ├── infrastructure/
│   │   │       │   │   │   ├── __init__.py
│   │   │       │   │   │   ├── models.py          # SQLAlchemy ORM: sessions, questions, answers, scores
│   │   │       │   │   │   ├── repositories.py   # SessionRepository impl
│   │   │       │   │   │   └── agents.py          # Pydantic AI: question_agent, feedback_agent, scoring_agent
│   │   │       │   │   └── presentation/
│   │   │       │   │       ├── __init__.py
│   │   │       │   │       ├── routers.py         # /api/v1/sessions/*
│   │   │       │   │       ├── schemas.py         # Request/response DTOs
│   │   │       │   │       ├── sse.py             # GET /api/v1/sessions/{id}/stream (SSE)
│   │   │       │   │       └── dependencies.py    # get_session, get_llm_provider
│   │   │       │   ├── installation/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── models.py              # installations, byok_configs, suppression_rules
│   │   │       │   │   ├── service.py             # CRUD, BYOK validation, GitHub App callbacks
│   │   │       │   │   ├── router.py              # /api/v1/installations/*
│   │   │       │   │   └── schemas.py
│   │   │       │   ├── identity/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── models.py              # github_users, oauth_tokens
│   │   │       │   │   ├── service.py             # GitHub OAuth flow, JWT issue/refresh
│   │   │       │   │   ├── router.py              # /api/v1/auth/*
│   │   │       │   │   └── schemas.py
│   │   │       │   ├── billing/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── models.py              # subscriptions, seat_usages
│   │   │       │   │   ├── service.py             # Lemon Squeezy API, seat counting
│   │   │       │   │   ├── router.py              # /api/v1/billing/*, /webhooks/lemonsqueezy
│   │   │       │   │   └── schemas.py
│   │   │       │   └── webhook/
│   │   │       │       ├── __init__.py
│   │   │       │       ├── router.py              # POST /webhooks/github
│   │   │       │       ├── verification.py        # HMAC SHA-256 signature check
│   │   │       │       ├── dispatcher.py          # Event type → handler routing
│   │   │       │       └── handlers.py            # pull_request.opened, .synchronize
│   │   │       └── admin/
│   │   │           ├── __init__.py
│   │   │           └── views.py                   # SQLAdmin model views
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── conftest.py                        # Fixtures: async db, test client, factories
│   │   │   ├── modules/
│   │   │   │   ├── comprehension/
│   │   │   │   │   ├── test_entities.py           # Domain entity unit tests
│   │   │   │   │   ├── test_handlers.py           # Use case integration tests
│   │   │   │   │   ├── test_agents.py             # Pydantic AI agent tests (mocked LLM)
│   │   │   │   │   └── test_routers.py            # API endpoint tests
│   │   │   │   ├── installation/
│   │   │   │   │   └── test_service.py
│   │   │   │   ├── identity/
│   │   │   │   │   └── test_service.py
│   │   │   │   └── webhook/
│   │   │   │       ├── test_verification.py
│   │   │   │       └── test_handlers.py
│   │   │   └── core/
│   │   │       ├── test_security.py
│   │   │       └── test_dependencies.py
│   │   ├── alembic/
│   │   │   ├── alembic.ini
│   │   │   ├── env.py
│   │   │   └── versions/                          # Migration files
│   │   ├── pyproject.toml                         # uv project config, dependencies, ruff config
│   │   ├── uv.lock
│   │   └── .python-version                        # 3.12
│   │
│   └── web/
│       ├── src/
│       │   ├── app.tsx                            # Router, QueryClientProvider, layout
│       │   ├── main.tsx                           # React root render
│       │   ├── vite-env.d.ts
│       │   ├── features/
│       │   │   ├── session/
│       │   │   │   ├── ChatView.tsx               # Main session page (split view)
│       │   │   │   ├── ChatMessage.tsx            # Single message bubble
│       │   │   │   ├── DiffViewer.tsx             # PR diff panel (right side)
│       │   │   │   ├── AnswerInput.tsx            # Text input + submit
│       │   │   │   ├── ScoreCard.tsx              # Final score display
│       │   │   │   ├── QuestionFeedback.tsx       # Per-question feedback
│       │   │   │   ├── useSessionStore.ts         # Zustand: chat state, messages, score
│       │   │   │   └── ChatView.test.tsx
│       │   │   ├── demo/
│       │   │   │   ├── DemoView.tsx               # Pre-loaded demo session
│       │   │   │   └── DemoView.test.tsx
│       │   │   ├── auth/
│       │   │   │   ├── OAuthCallback.tsx          # GitHub OAuth redirect handler
│       │   │   │   ├── useAuthStore.ts            # Zustand: JWT, user, login state
│       │   │   │   └── ProtectedRoute.tsx         # Auth guard component
│       │   │   ├── installation/
│       │   │   │   ├── SetupView.tsx              # BYOK config, suppression labels
│       │   │   │   └── SettingsView.tsx           # Installation settings
│       │   │   └── landing/
│       │   │       ├── LandingPage.tsx            # Homepage with demo CTA
│       │   │       └── InstallCTA.tsx             # GitHub App install button
│       │   ├── shared/
│       │   │   ├── components/
│       │   │   │   ├── Button.tsx
│       │   │   │   ├── Input.tsx
│       │   │   │   ├── Toast.tsx
│       │   │   │   ├── LoadingSpinner.tsx
│       │   │   │   └── SplitPane.tsx              # Resizable split view layout
│       │   │   ├── hooks/
│       │   │   │   ├── useSSE.ts                  # SSE connection + reconnection + parsing
│       │   │   │   └── useApi.ts                  # Axios/fetch wrapper with JWT refresh
│       │   │   ├── api/
│       │   │   │   ├── client.ts                  # API client config (base URL, interceptors)
│       │   │   │   ├── queries.ts                 # TanStack Query hooks
│       │   │   │   └── types.ts                   # Generated from OpenAPI (openapi-typescript)
│       │   │   └── theme/
│       │   │       └── tokens.ts                  # Design tokens (colors, fonts, spacing)
│       │   └── index.css                          # Tailwind directives + global styles
│       ├── public/
│       │   └── fonts/                             # Berkeley Mono font files
│       ├── index.html
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       ├── tailwind.config.ts
│       └── eslint.config.js
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api                         # Multi-stage: uv install → uvicorn
│   │   └── Dockerfile.web                         # Multi-stage: npm build → nginx
│   └── coolify/
│       └── docker-compose.prod.yml                # Production compose for Coolify
│
├── docker-compose.yml                             # Local dev: api + web + db
├── Makefile                                       # dev, test, lint, build, migrate, types
├── .env.example                                   # Template for all env vars
├── .gitignore
└── README.md
```

### Requirements to Structure Mapping

| FR Category | Backend Location | Frontend Location |
|------------|-----------------|-------------------|
| FR1-5 (Session Lifecycle) | `webhook/` → `comprehension/application/handlers.py` → `comprehension/presentation/routers.py` | `features/session/ChatView.tsx`, `features/auth/OAuthCallback.tsx` |
| FR6-11 (Socratic Challenge) | `comprehension/infrastructure/agents.py`, `comprehension/domain/services.py`, `comprehension/presentation/sse.py` | `features/session/ChatMessage.tsx`, `shared/hooks/useSSE.ts` |
| FR12-16 (Scoring & Feedback) | `comprehension/domain/entities.py` (Score), `comprehension/infrastructure/agents.py` (scoring_agent) | `features/session/ScoreCard.tsx`, `features/session/QuestionFeedback.tsx` |
| FR17-19 (Question Quality) | `comprehension/application/commands.py` (ReportQuestion), `comprehension/infrastructure/models.py` | Report button in `ChatMessage.tsx`, feedback in `ScoreCard.tsx` |
| FR20-24 (Installation & Config) | `installation/` module (all files) | `features/installation/SetupView.tsx`, `features/installation/SettingsView.tsx` |
| FR25-27 (Auth) | `identity/` module, `core/dependencies.py`, `core/security.py` | `features/auth/`, `shared/hooks/useApi.ts` |
| FR28-30 (Demo) | `comprehension/presentation/routers.py` (demo endpoint, no auth) | `features/demo/DemoView.tsx`, `features/landing/LandingPage.tsx` |
| FR31-33 (Billing) | `billing/` module | Redirect to Lemon Squeezy checkout (no custom billing UI in MVP) |
| FR34-38 (Data & Privacy) | `core/security.py` (encryption), `webhook/verification.py` (HMAC), `comprehension/infrastructure/agents.py` (zero-retention via BYOK) | N/A (backend-only concerns) |

### Integration Boundaries

**External Integration Map:**

```
GitHub ←→ helprs
  ├── Webhooks IN:  POST /webhooks/github        (webhook/ module)
  ├── OAuth:        GET  /api/v1/auth/github      (identity/ module)
  ├── REST OUT:     Fetch diffs, post comments    (comprehension/infrastructure/)
  └── App Install:  GitHub redirect flow          (installation/ module)

Anthropic Claude API ←→ helprs
  └── LLM calls:    Via user's BYOK key           (comprehension/infrastructure/agents.py)

Lemon Squeezy ←→ helprs
  ├── Webhooks IN:  POST /webhooks/lemonsqueezy   (billing/ module)
  └── Checkout:     Redirect to LS checkout       (billing/router.py)
```

**Core Session Data Flow:**

```
PR opened → GitHub webhook → webhook/router.py
  → verify HMAC (webhook/verification.py)
  → persist event (webhook/handlers.py)
  → BackgroundTask: create session
    → comprehension/application/handlers.py (StartSession)
    → fetch diff via GitHub API
    → post PR comment with session links
    → session ready in DB

User clicks link → OAuth → JWT → GET /sessions/{id}
  → load session + diff → render ChatView (split view)

User in session → SSE stream /sessions/{id}/stream
  → Pydantic AI agent generates question → stream tokens → SSE event
  → User submits answer → POST /sessions/{id}/answers
  → Pydantic AI agent evaluates → stream feedback → SSE event
  → Repeat for N questions
  → Pydantic AI scoring agent → final score → SSE score event
  → POST GitHub status check (informational)
```

## Architecture Validation Results

### Coherence Validation

**Decision Compatibility:** All technology choices are within the same ecosystems (Pydantic/FastAPI, Astral uv/ruff, React/Vite/Zustand/TanStack). No version conflicts detected. Pydantic AI 1.77.0 natively supports Anthropic Claude and integrates with Pydantic v2 used by FastAPI.

**Pattern Consistency:** snake_case flows consistently from DB → API → Python code. Frontend follows React conventions (PascalCase components, camelCase functions). DDD hybrid approach is internally consistent -- full layers only where complexity warrants it.

**Structure Alignment:** Project structure directly maps to architectural decisions. Each module has clear boundaries. The dependency rule (presentation → application → domain ← infrastructure) is enforceable through import conventions.

### Requirements Coverage

**Functional Requirements:** 38/38 FRs fully covered by architectural decisions and mapped to specific files/directories in the project structure.

**Non-Functional Requirements:**
- Performance: Async FastAPI + Pydantic AI streaming + SSE covers <1s first token and <3s first question targets
- Security: Fernet encryption (BYOK), HMAC verification (webhooks), JWT + httpOnly cookies (auth), zero code retention (in-memory diff processing)
- Scalability: Stateless API (JWT), PostgreSQL-backed state, Docker containers enable horizontal scaling
- Reliability: DB event persistence covers webhook crash recovery, session state survives restarts via PostgreSQL

### Gap Analysis

**Critical Gaps:** 0

**Important Gaps:**
1. Database schema details (tables, columns, relations) -- will be defined during implementation via Alembic migrations. Domain entities provide the blueprint
2. Demo mode seed data (pre-loaded session for FR28-29) -- requires a fixture/seed script, to be created in the demo story

**Nice-to-Have:**
1. Makefile target documentation -- will be created during scaffolding story
2. OpenAPI → TypeScript pipeline automation (`make types`) -- will be formalized during frontend setup

### Architecture Completeness Checklist

**Requirements Analysis:**
- [x] Project context thoroughly analyzed (38 FRs, 22 NFRs)
- [x] Scale and complexity assessed (Medium-High)
- [x] Technical constraints identified (BYOK, 2-person team, no RAG)
- [x] Cross-cutting concerns mapped (security, observability, compliance, rate limiting)

**Architectural Decisions:**
- [x] Critical decisions documented with verified versions
- [x] Technology stack fully specified (backend, frontend, infrastructure, integrations)
- [x] Integration patterns defined (GitHub, Anthropic, Lemon Squeezy)
- [x] Performance considerations addressed

**Implementation Patterns:**
- [x] Naming conventions established (DB, API, Python, TypeScript)
- [x] Structure patterns defined (tests, imports, file organization)
- [x] Communication patterns specified (SSE events, Zustand stores)
- [x] Process patterns documented (error handling, loading states)

**Project Structure:**
- [x] Complete directory structure defined with all files
- [x] Component boundaries established (modules, layers, features)
- [x] Integration points mapped (external + internal data flow)
- [x] Requirements to structure mapping complete (38 FRs → specific files)

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High

**Key Strengths:**
- DDD hybrid avoids over-engineering while maintaining clean architecture for the core domain
- Pydantic AI provides type-safe LLM interactions with built-in streaming and model-agnostic support
- Astral toolchain (uv + ruff) simplifies Python development workflow
- Complete FR → file mapping enables any AI agent to know exactly where to implement each requirement
- PostgreSQL-only data layer avoids infrastructure complexity for MVP

**Areas for Future Enhancement:**
- Redis caching layer if DB performance becomes a bottleneck
- arq/Celery queue if BackgroundTasks reliability is insufficient at scale
- CDN for frontend static assets when traffic grows
- Multi-LLM support is architecturally ready via Pydantic AI (config change only)
- Admin dashboard (Phase 2) will require promoting installation module to full DDD if complexity grows

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect project structure and module boundaries
- Refer to this document for all architectural questions
- Domain layer must remain framework-free (pure Python + Pydantic only)
- Use Pydantic AI agents for all LLM interactions (never raw API calls)

**First Implementation Priority:**
```bash
# Story 1: Project scaffolding
mkdir -p helprs/{apps/api,apps/web,infra}
cd helprs/apps/api && uv init --python 3.12
# ... (full commands documented in Starter Template Evaluation section)
```

**Implementation Sequence:**
1. Project scaffolding (monorepo, Docker Compose, CI, Makefile)
2. Core infrastructure (database, config, auth middleware, exception handling)
3. Identity module (GitHub OAuth flow, JWT)
4. Installation module (GitHub App install, BYOK config)
5. Webhook module (GitHub event reception + dispatch)
6. Comprehension module (sessions, Pydantic AI agents, scoring, SSE)
7. Frontend (auth → session UI → demo → landing)
8. Billing module (Lemon Squeezy integration)
