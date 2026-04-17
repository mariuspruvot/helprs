# Source Tree Analysis

> Updated 2026-04-17 (post-cleanup)

## Repository Structure

```
helprs/                              # Monorepo root
+-- apps/
|   +-- api/                         # FastAPI Backend (Python 3.12)
|   |   +-- alembic/                 # Database migrations
|   |   |   +-- env.py               # Migration runtime config
|   |   |   +-- versions/            # Migration files (10 revisions)
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
|   |   |   +-- modules/             # Domain modules (all flat)
|   |   |       +-- identity/        # GitHub OAuth + user management
|   |   |       |   +-- router.py    # /api/v1/auth/* endpoints
|   |   |       |   +-- service.py   # OAuth flow, token management
|   |   |       |   +-- models.py    # GitHubUser SQLAlchemy model
|   |   |       |   +-- schemas.py   # UserResponse, TokenResponse
|   |   |       +-- installation/    # GitHub App installation management
|   |   |       |   +-- router.py    # /api/v1/installations/* endpoints
|   |   |       |   +-- service.py   # Credential validation, label management
|   |   |       |   +-- models.py    # Installation, BYOKConfig models
|   |   |       |   +-- schemas.py   # Installation request/response schemas
|   |   |       +-- webhook/         # GitHub webhook processing
|   |   |       |   +-- router.py    # /api/v1/webhooks/github endpoint
|   |   |       |   +-- handlers.py  # Event-specific handlers
|   |   |       |   +-- dispatcher.py # Event routing + retry logic
|   |   |       |   +-- verification.py # HMAC signature verification
|   |   |       |   +-- tasks.py     # Background task execution
|   |   |       |   +-- repository.py # WebhookEvent CRUD
|   |   |       |   +-- models.py    # WebhookEvent model
|   |   |       +-- container/       # Container orchestration
|   |   |           +-- router.py    # Session + SSE relay endpoints
|   |   |           +-- service.py   # Container lifecycle management
|   |   |           +-- models.py    # ContainerSession model
|   |   |           +-- schemas.py   # Request/response schemas
|   |   +-- tests/                   # Test suite
|   |   |   +-- conftest.py          # Sets env vars BEFORE imports
|   |   |   +-- test_health.py       # Health endpoint test
|   |   |   +-- core/                # Core module tests
|   |   |   |   +-- test_config.py
|   |   |   |   +-- test_database.py
|   |   |   |   +-- test_dependencies.py
|   |   |   |   +-- test_exceptions.py
|   |   |   |   +-- test_logging.py
|   |   |   |   +-- test_middleware.py
|   |   |   |   +-- test_security.py
|   |   |   +-- modules/
|   |   |   |   +-- identity/       # Auth tests
|   |   |   |   +-- installation/   # Installation + BYOK + suppression tests
|   |   |   |   +-- webhook/        # Webhook tests
|   |   |   |   +-- container/      # Container tests
|   |   |   +-- integration/
|   |   |       +-- test_container_flow.py
|   |   +-- pyproject.toml          # Project config (uv, ruff, pytest)
|   |   +-- alembic.ini
|   |
|   +-- web/                         # React Frontend (TypeScript)
|       +-- src/
|       |   +-- main.tsx             # Entry point -- ReactDOM.createRoot
|       |   +-- app.tsx              # App component -- routes + providers
|       |   +-- app.test.tsx         # App routing tests
|       |   +-- index.css            # Global styles (Tailwind 4)
|       |   +-- vite-env.d.ts        # Vite type declarations
|       |   +-- features/            # Feature modules
|       |   |   +-- auth/            # OAuth flow + auth state
|       |   |   |   +-- store.ts     # Zustand auth store
|       |   |   |   +-- OAuthCallback.tsx
|       |   |   |   +-- ProtectedRoute.tsx
|       |   |   +-- landing/         # Marketing page
|       |   |   |   +-- LandingPage.tsx
|       |   |   |   +-- LandingPage.test.tsx
|       |   |   |   +-- InstallCTA.tsx
|       |   |   |   +-- InstallCTA.test.tsx
|       |   |   +-- demo/            # Reserved (.gitkeep only)
|       |   |   +-- installation/    # Setup + settings views
|       |   |   |   +-- SetupView.tsx
|       |   |   |   +-- SettingsView.tsx
|       |   |   +-- session/         # Container skill execution
|       |   |       +-- SessionView.tsx
|       |   |       +-- SkillSelector.tsx
|       |   |       +-- SkillSelector.test.tsx
|       |   |       +-- ContainerSession.tsx
|       |   |       +-- ContainerSession.test.tsx
|       |   |       +-- TerminalOutput.tsx
|       |   |       +-- TerminalOutput.test.tsx
|       |   |       +-- containerApi.ts
|       |   |       +-- containerTypes.ts
|       |   +-- shared/              # Shared infrastructure
|       |       +-- api/client.ts    # apiFetch wrapper (auth, retry, refresh)
|       |       +-- components/      # Empty (.gitkeep only)
|       +-- public/
|       |   +-- favicon.svg
|       |   +-- icons.svg
|       |   +-- fonts/               # Empty (.gitkeep only)
|       +-- package.json
|       +-- package-lock.json
|       +-- tsconfig.json
|       +-- vite.config.ts
|       +-- eslint.config.js
|       +-- nginx.conf               # Production static file serving
|       +-- index.html
|
+-- skills/                          # Skill definitions
|   +-- challenge-me/                # Socratic quiz on PR changes
|   |   +-- CLAUDE.md
|   |   +-- prompt.md
|   |   +-- config.yaml
|   +-- README.md
|   +-- SKILL_SPEC.md                # Skill authoring specification
|
+-- infra/                           # Infrastructure
|   +-- docker/
|   |   +-- Dockerfile.api           # Python multi-stage (dev/production)
|   |   +-- Dockerfile.web           # Node multi-stage (dev/build/production)
|   |   +-- claude-runner/           # Ephemeral Claude Code container
|   |   |   +-- Dockerfile
|   |   |   +-- entrypoint.sh
|   |   +-- nginx.conf               # SPA routing + asset caching
|   +-- coolify/
|       +-- docker-compose.prod.yml  # Production compose (Coolify)
|
+-- docs/                            # Project documentation
|   +-- adr-001-claude-code-container-pivot.md
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
|   +-- assets/
|
+-- .github/workflows/
|   +-- ci.yml                       # CI: lint + test + build gate
|   +-- deploy.yml                   # CD: GHCR push + Coolify webhook
|
+-- docker-compose.yml               # Dev environment (api:8000, web:5173, db:5432)
+-- Makefile                         # dev, lint, test, build, migrate targets
+-- mkdocs.yml                       # Documentation site config
+-- CLAUDE.md                        # AI assistant instructions
+-- PROJECT-STATUS.md                # Detailed project status
+-- README.md                        # Project README
```

## Critical Folders

| Path | Purpose | Key Files |
|------|---------|-----------|
| `apps/api/src/helprs/core/` | Framework foundation -- config, DB, auth, middleware | `config.py`, `security.py`, `dependencies.py` |
| `apps/api/src/helprs/modules/container/` | Container orchestration + session tracking | `service.py`, `router.py`, `models.py` |
| `apps/api/src/helprs/modules/webhook/` | GitHub webhook ingestion pipeline | `handlers.py`, `dispatcher.py`, `verification.py` |
| `apps/web/src/features/session/` | Container session UI -- skill selection, terminal output | `ContainerSession.tsx`, `SkillSelector.tsx`, `TerminalOutput.tsx` |
| `apps/web/src/shared/api/` | API client with auth token management | `client.ts` |
| `skills/` | Skill definitions for Claude Code | `challenge-me/` (first skill) |
| `infra/docker/claude-runner/` | Ephemeral container image definition | `Dockerfile`, `entrypoint.sh` |
| `.github/workflows/` | CI/CD pipeline | `ci.yml`, `deploy.yml` |
