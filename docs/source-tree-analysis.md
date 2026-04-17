# Source Tree Analysis

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Repository Structure

```
helprs/                              # Monorepo root
+-- apps/
|   +-- api/                         # FastAPI Backend (Python 3.12)
|   |   +-- alembic/                 # Database migrations
|   |   |   +-- env.py               # Migration runtime config
|   |   |   +-- versions/            # Migration files
|   |   +-- src/helprs/              # Application source
|   |   |   +-- main.py              # Entry point -- create_app() factory
|   |   |   +-- admin/               # SQLAdmin panel views
|   |   |   |   +-- views.py         # Admin model views
|   |   |   +-- core/                # Framework foundation
|   |   |   |   +-- config.py        # Pydantic Settings (env vars)
|   |   |   |   +-- database.py      # AsyncEngine + async_sessionmaker
|   |   |   |   +-- dependencies.py  # FastAPI Depends (get_db, get_current_user)
|   |   |   |   +-- exceptions.py    # Custom HTTP exceptions + handlers
|   |   |   |   +-- middleware.py     # CORS, timing, Sentry middleware
|   |   |   |   +-- security.py      # JWT encode/decode, Fernet encrypt/decrypt
|   |   |   +-- modules/             # Domain modules
|   |   |       +-- identity/        # GitHub OAuth + user management (flat)
|   |   |       |   +-- router.py    # /api/v1/auth/* endpoints
|   |   |       |   +-- service.py   # OAuth flow, token management
|   |   |       |   +-- models.py    # GitHubUser SQLAlchemy model
|   |   |       |   +-- schemas.py   # UserResponse, TokenResponse
|   |   |       +-- installation/    # GitHub App installation management (flat)
|   |   |       |   +-- router.py    # /api/v1/installations/* endpoints
|   |   |       |   +-- service.py   # Credential validation, label management
|   |   |       |   +-- models.py    # Installation, BYOKConfig models
|   |   |       |   +-- schemas.py   # Installation request/response schemas
|   |   |       +-- webhook/         # GitHub webhook processing (flat)
|   |   |       |   +-- router.py    # /api/v1/webhooks/github endpoint
|   |   |       |   +-- handlers.py  # Event-specific handlers
|   |   |       |   +-- dispatcher.py # Event routing + retry logic
|   |   |       |   +-- verification.py # HMAC signature verification
|   |   |       |   +-- tasks.py     # Background task execution
|   |   |       |   +-- repository.py # WebhookEvent CRUD
|   |   |       |   +-- models.py    # WebhookEvent model
|   |   |       +-- container/       # NEW: container orchestration (Coming in Phase 2)
|   |   |           +-- router.py    # Session + SSE relay endpoints
|   |   |           +-- service.py   # Container lifecycle management
|   |   |           +-- orchestrator.py # Docker SDK integration
|   |   |           +-- models.py    # ContainerSession model
|   |   |           +-- schemas.py   # Request/response schemas
|   |   +-- tests/                   # Test suite
|   |   |   +-- conftest.py          # Sets env vars BEFORE imports
|   |   |   +-- core/               # Core module tests
|   |   |   +-- modules/
|   |   |       +-- identity/       # Auth tests
|   |   |       +-- installation/   # Installation tests
|   |   |       +-- webhook/        # Webhook tests
|   |   |       +-- container/      # Container tests (Coming in Phase 2)
|   |   +-- pyproject.toml          # Project config (uv, ruff, pytest)
|   |
|   +-- web/                         # React Frontend (TypeScript)
|       +-- src/
|       |   +-- main.tsx             # Entry point -- ReactDOM.createRoot
|       |   +-- app.tsx              # App component -- routes + providers
|       |   +-- index.css            # Global styles (Tailwind 4 + custom tokens)
|       |   +-- features/            # Feature modules
|       |   |   +-- auth/            # OAuth flow + auth state
|       |   |   |   +-- store.ts     # Zustand auth store
|       |   |   |   +-- OAuthCallback.tsx
|       |   |   |   +-- ProtectedRoute.tsx
|       |   |   +-- landing/         # Marketing page
|       |   |   |   +-- LandingPage.tsx
|       |   |   |   +-- InstallCTA.tsx
|       |   |   +-- dashboard/       # Installation grid
|       |   |   |   +-- DashboardPage.tsx
|       |   |   +-- installation/    # Setup + settings views
|       |   |   |   +-- SetupView.tsx
|       |   |   |   +-- SettingsView.tsx
|       |   |   +-- session/         # Container result display (adapting)
|       |   |       +-- store.ts     # Zustand session UI state
|       |   |       +-- hooks/       # Session-specific hooks
|       |   +-- shared/              # Shared infrastructure
|       |       +-- api/client.ts    # apiFetch wrapper (auth, retry, refresh)
|       |       +-- components/
|       |       |   +-- AppShell.tsx  # Top nav bar + layout wrapper
|       |       +-- hooks/
|       |       |   +-- useSSE.ts    # EventSource wrapper
|       |       |   +-- parseSSE.ts  # SSE stream consumer
|       |       |   +-- useViewport.ts
|       |       |   +-- useReducedMotion.ts
|       |       +-- theme/tokens.ts  # Design system tokens
|       |       +-- types/
|       |       +-- utils/
|       +-- package.json
|       +-- tsconfig.json
|       +-- vite.config.ts
|       +-- nginx.conf               # Production static file serving
|
+-- skills/                          # Skill definitions (Coming in Phase 2)
|   +-- challenge-me/                # Socratic quiz on PR changes
|   +-- code-review/                 # Multi-layer adversarial code review
|   +-- security-audit/              # Vulnerability scan on diff
|   +-- doc-generator/               # Generate/update documentation
|   +-- test-suggester/              # Propose missing test cases
|
+-- infra/                           # Infrastructure
|   +-- docker/
|   |   +-- Dockerfile.api           # Python multi-stage (dev/production)
|   |   +-- Dockerfile.web           # Node multi-stage (dev/build/production)
|   |   +-- Dockerfile.claude-runner # Claude Code CLI container (Coming in Phase 2)
|   |   +-- nginx.conf               # SPA routing + asset caching
|   +-- coolify/
|       +-- docker-compose.prod.yml  # Production compose (Coolify)
|
+-- docs/                            # Project documentation
|   +-- adr-001-claude-code-container-pivot.md  # Architecture decision record
|   +-- project-overview.md
|   +-- architecture-api.md
|   +-- architecture-web.md
|   +-- architecture-infra.md
|   +-- integration-architecture.md
|   +-- api-contracts-api.md
|   +-- data-models-api.md
|   +-- component-inventory-web.md
|   +-- source-tree-analysis.md
|   +-- development-guide.md
|   +-- deployment-guide.md
|   +-- index.md
|
+-- .github/workflows/
|   +-- ci.yml                       # CI: lint + test (4 parallel) + build gate
|   +-- deploy.yml                   # CD: GHCR push + Coolify webhook
|
+-- docker-compose.yml               # Dev environment (api:8000, web:5173, db:5432)
+-- docker-compose.override.yml      # Dev secrets (GitHub App private key)
+-- Makefile                         # dev, lint, test, build, migrate targets
+-- mkdocs.yml                       # Documentation site config
+-- CLAUDE.md                        # AI assistant instructions
+-- README.md                        # Project README
```

## Critical Folders

| Path | Purpose | Key Files |
|------|---------|-----------|
| `apps/api/src/helprs/core/` | Framework foundation -- config, DB, auth, middleware | `config.py`, `security.py`, `dependencies.py` |
| `apps/api/src/helprs/modules/container/` | Container orchestration (Phase 2) | `orchestrator.py`, `service.py`, `router.py` |
| `apps/api/src/helprs/modules/webhook/` | GitHub webhook ingestion pipeline | `handlers.py`, `dispatcher.py`, `verification.py` |
| `apps/web/src/features/session/` | Container result display UI | Adapting for container output |
| `apps/web/src/shared/api/` | API client with auth token management | `client.ts` |
| `skills/` | Skill definitions for Claude Code (Phase 2) | Per-skill agent folders |
| `infra/docker/` | Container build definitions | `Dockerfile.api`, `Dockerfile.web`, `Dockerfile.claude-runner` |
| `.github/workflows/` | CI/CD pipeline | `ci.yml`, `deploy.yml` |

## Removed (Post-Pivot)

| Path | Was | Reason |
|------|-----|--------|
| `apps/api/src/helprs/modules/comprehension/` | DDD module (domain/application/infrastructure/presentation) | Replaced by container-based skill execution |
| `apps/api/src/helprs/modules/billing/` | Empty billing stub | Removed per open-source pivot |
| `tests/modules/comprehension/` | Comprehension module tests | Module removed |
