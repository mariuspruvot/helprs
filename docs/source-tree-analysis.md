# Source Tree Analysis

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Annotated Directory Tree

```
helprs/                              # Project root (monorepo)
├── apps/
│   ├── api/                         # Part: api (FastAPI Backend)
│   │   ├── src/helprs/
│   │   │   ├── main.py              # ★ Entry point — create_app() factory
│   │   │   ├── core/
│   │   │   │   ├── config.py        # Settings (pydantic-settings, .env)
│   │   │   │   ├── database.py      # Async engine + session factory
│   │   │   │   ├── dependencies.py  # DI: get_db, get_current_user, get_settings
│   │   │   │   ├── middleware.py     # Request logging middleware
│   │   │   │   └── security.py      # JWT creation/validation, Fernet encryption
│   │   │   ├── modules/
│   │   │   │   ├── identity/        # GitHub OAuth + user management
│   │   │   │   │   ├── router.py    # /auth/* endpoints
│   │   │   │   │   ├── service.py   # OAuth flow, token management
│   │   │   │   │   ├── models.py    # GitHubUser model
│   │   │   │   │   └── schemas.py   # UserResponse, TokenResponse
│   │   │   │   ├── installation/    # GitHub App installation management
│   │   │   │   │   ├── router.py    # /installations/* endpoints
│   │   │   │   │   ├── service.py   # BYOK, suppression labels
│   │   │   │   │   ├── models.py    # Installation, BYOKConfig models
│   │   │   │   │   └── schemas.py   # InstallationResponse, BYOKRequest
│   │   │   │   ├── webhook/         # GitHub webhook processing
│   │   │   │   │   ├── router.py    # /webhooks/github endpoint
│   │   │   │   │   ├── service.py   # Event dispatch, crash-replay, reaper
│   │   │   │   │   ├── models.py    # WebhookEvent model
│   │   │   │   │   └── schemas.py   # Webhook DTOs
│   │   │   │   ├── billing/         # Billing module (stub, removed per open-source pivot)
│   │   │   │   └── comprehension/   # ★ Core feature — Socratic sessions (Clean Architecture)
│   │   │   │       ├── domain/
│   │   │   │       │   ├── entities.py       # Session, Question, Answer, Score dataclasses
│   │   │   │       │   ├── value_objects.py   # SessionRole, SessionStatus, Verdict, Topic enums
│   │   │   │       │   ├── interfaces.py      # Protocol: SessionRepository, LLMProvider
│   │   │   │       │   └── services.py        # estimate_question_count, derive_verdict
│   │   │   │       ├── application/
│   │   │   │       │   ├── commands.py        # StartSessionCommand
│   │   │   │       │   ├── queries.py         # GetSessionQuery, GetSessionResult
│   │   │   │       │   └── handlers.py        # StartSessionHandler, GetSessionHandler
│   │   │   │       ├── infrastructure/
│   │   │   │       │   ├── models.py          # Session, Question, Answer, Score ORM models
│   │   │   │       │   ├── repositories.py    # SqlAlchemySessionRepository
│   │   │   │       │   ├── agents.py          # PydanticAILLMProvider (Claude Sonnet)
│   │   │   │       │   ├── github_diff.py     # Diff fetching (streaming, 1MB cap)
│   │   │   │       │   └── diff_refs.py       # Diff parsing, file-ref extraction
│   │   │   │       └── presentation/
│   │   │   │           ├── routers.py         # GET session, POST report, POST feedback
│   │   │   │           ├── sse.py             # ★ SSE streaming: GET /stream, POST /answers
│   │   │   │           ├── schemas.py         # SessionResponse, ScoreResponse
│   │   │   │           ├── dependencies.py    # get_llm_provider factory
│   │   │   │           └── answer_pubsub.py   # In-process ephemeral text registry
│   │   │   └── admin/
│   │   │       └── views.py          # SQLAdmin panel views
│   │   ├── tests/                    # Mirrors modules/ structure
│   │   │   └── modules/
│   │   │       ├── identity/
│   │   │       ├── installation/
│   │   │       ├── webhook/
│   │   │       └── comprehension/
│   │   ├── alembic/                  # DB migrations
│   │   │   └── versions/             # 9 migration files
│   │   ├── pyproject.toml            # Python project config (uv, ruff, pytest)
│   │   └── alembic.ini               # Alembic config
│   │
│   └── web/                          # Part: web (React Frontend)
│       ├── src/
│       │   ├── app.tsx               # ★ Entry point — Router + QueryClient
│       │   ├── features/
│       │   │   ├── auth/             # GitHub OAuth flow
│       │   │   │   ├── OAuthCallback.tsx   # OAuth return handler
│       │   │   │   ├── ProtectedRoute.tsx  # Auth guard
│       │   │   │   └── store.ts            # useAuthStore (Zustand)
│       │   │   ├── installation/     # Setup wizard + settings
│       │   │   │   ├── SetupView.tsx       # 3-step setup wizard
│       │   │   │   └── SettingsView.tsx    # BYOK + labels CRUD
│       │   │   ├── landing/          # Marketing landing page
│       │   │   │   ├── LandingPage.tsx     # Hero, how-it-works, BYOK, CTA
│       │   │   │   └── InstallCTA.tsx      # GitHub App install button
│       │   │   ├── session/          # ★ Core feature — 17 components
│       │   │   │   ├── ChatView.tsx        # Top-level session page
│       │   │   │   ├── ChatPanel.tsx       # Message list + SSE + submit
│       │   │   │   ├── ChatMessage.tsx     # Markdown chat bubble
│       │   │   │   ├── AnswerInput.tsx     # Auto-resizing textarea
│       │   │   │   ├── SessionHeader.tsx   # Header bar with progress
│       │   │   │   ├── DiffViewer.tsx      # Unified diff viewer
│       │   │   │   ├── SplitLayout.tsx     # Desktop resizable split
│       │   │   │   ├── TabbedLayout.tsx    # Tablet tabbed layout
│       │   │   │   ├── MobileLayout.tsx    # Mobile chat-only
│       │   │   │   ├── CodeLink.tsx        # Inline file:line link
│       │   │   │   ├── ScoreCard.tsx       # Comprehension score display
│       │   │   │   ├── ReportButton.tsx    # Question report flag
│       │   │   │   ├── SessionFeedback.tsx # Post-session thumbs + comment
│       │   │   │   ├── store.ts            # useSessionStore (Zustand)
│       │   │   │   ├── api.ts              # fetchSession
│       │   │   │   ├── types.ts            # Wire types (hand-synced)
│       │   │   │   └── refractorSetup.ts   # Syntax highlighting (10 langs)
│       │   │   └── demo/              # (placeholder)
│       │   └── shared/
│       │       ├── api/client.ts      # apiFetch: authenticated fetch wrapper
│       │       ├── hooks/
│       │       │   ├── useViewport.ts      # Desktop/tablet/mobile detection
│       │       │   ├── useReducedMotion.ts # prefers-reduced-motion
│       │       │   ├── useSSE.ts           # EventSource with reconnection
│       │       │   └── parseSSE.ts         # ReadableStream SSE parser
│       │       └── theme/tokens.ts    # Design tokens (dark theme, amber)
│       ├── package.json               # Dependencies + scripts
│       └── tsconfig.json              # TypeScript config (ES2023, strict)
│
├── infra/                             # Part: infra (Docker/Coolify)
│   ├── docker/
│   │   ├── Dockerfile.api             # Multi-stage: dev + production
│   │   ├── Dockerfile.web             # Multi-stage: dev + build + production
│   │   └── nginx.conf                 # SPA fallback + asset caching
│   └── coolify/
│       └── docker-compose.prod.yml    # Production compose (3 services)
│
├── .github/workflows/
│   ├── ci.yml                         # Lint + test + build (4 parallel + gated)
│   └── deploy.yml                     # Build + push to GHCR + Coolify webhook
│
├── docker-compose.yml                 # Local dev compose
├── docker-compose.override.yml        # RSA key injection (YAML block scalar)
├── Makefile                           # dev, lint, test, build, migrate
├── .env.example                       # Environment variable documentation
├── CLAUDE.md                          # AI development context
├── design/                            # Design assets
└── challenge-me/                      # Side project / experiments
```

## Critical Folders Summary

| Folder | Part | Purpose |
|--------|------|---------|
| `apps/api/src/helprs/core/` | api | Config, DB, DI, middleware, security |
| `apps/api/src/helprs/modules/comprehension/` | api | Core business logic (Clean Architecture) |
| `apps/api/src/helprs/modules/identity/` | api | GitHub OAuth + user management |
| `apps/api/src/helprs/modules/installation/` | api | BYOK + installation config |
| `apps/api/src/helprs/modules/webhook/` | api | Webhook processing + durability |
| `apps/web/src/features/session/` | web | Core comprehension UI (17 components) |
| `apps/web/src/features/auth/` | web | OAuth flow + auth state |
| `apps/web/src/shared/` | web | API client, hooks, design tokens |
| `infra/docker/` | infra | Dockerfiles + nginx config |
| `.github/workflows/` | infra | CI/CD pipelines |
