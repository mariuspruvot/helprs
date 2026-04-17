# Architecture -- Backend (api)

> Updated 2026-04-17 (post-cleanup)

## Executive Summary

FastAPI backend serving as a container orchestrator, webhook receiver, and admin panel for helPRs. The backend does **not** run AI logic -- all AI execution happens inside ephemeral Docker containers running Claude Code CLI. The backend's role is to receive GitHub webhooks, manage installations/credentials, provision containers, and relay container output (SSE passthrough) to the frontend.

## Technology Stack

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| Language | Python | 3.12 | Runtime |
| Framework | FastAPI | >= 0.115 | HTTP framework |
| ORM | SQLAlchemy | >= 2.0.36 | Async ORM (asyncpg driver) |
| Migrations | Alembic | >= 1.14 | Schema migrations |
| Settings | Pydantic Settings | >= 2.7 | Typed env var config |
| Container | aiodocker | >= 0.23 | Async Docker client for ephemeral container lifecycle |
| Logging | structlog | >= 24.4 | Structured logging |
| Monitoring | Sentry SDK | >= 2.19 | Error tracking |
| Rate Limiting | SlowAPI | >= 0.1.9 | Per-IP rate limiting |
| Auth | python-jose | >= 3.3 | JWT encoding/decoding |
| Encryption | cryptography | >= 44.0 | Fernet symmetric encryption |
| HTTP Client | httpx | >= 0.28 | GitHub API calls |
| Admin | SQLAdmin | >= 0.20 | Admin panel + credential management |
| Testing | pytest + pytest-asyncio | >= 8.3 | Test framework |
| Linting | ruff | >= 0.8 | Linter + formatter |

## Architecture Pattern

```
+---------------------------------------------+
|                 main.py                      |
|            create_app() factory              |
|                                              |
|  Lifespan: DB engine init + cleanup          |
|  Middleware: CORS, Timing, Sentry            |
|  Routers: health, auth, installations,       |
|           webhooks, containers               |
|  Admin: SQLAdmin panel at /admin             |
+---------------------------------------------+
         |
         +-- core/           (Framework foundation)
         |   +-- config.py        Settings from env vars
         |   +-- database.py      AsyncEngine + sessionmaker
         |   +-- dependencies.py  get_db, get_current_user
         |   +-- exceptions.py    HTTP exception handlers
         |   +-- middleware.py     CORS, timing
         |   +-- security.py      JWT, Fernet, HMAC
         |
         +-- modules/        (All flat pattern)
             +-- identity/       (router -> service -> model)
             +-- installation/   (router -> service -> model)
             +-- webhook/        (router -> dispatcher -> handlers -> model)
             +-- container/      (router -> service -> model)
```

### Flat Module Pattern

All four modules use the same structure:

```
module/
+-- router.py    # FastAPI router (HTTP endpoints)
+-- service.py   # Business logic (called by router)
+-- models.py    # SQLAlchemy models
+-- schemas.py   # Pydantic request/response schemas
```

The webhook module adds `dispatcher.py`, `handlers.py`, `verification.py`, `tasks.py`, and `repository.py` for its event processing pipeline.

## Backend Role

The backend is a **thin orchestrator**, not an AI host:

| Responsibility | Description |
|----------------|-------------|
| Webhook receiver | Receives GitHub PR events, creates session records, posts PR comments |
| Credential manager | Stores Claude credentials (Fernet-encrypted), injects into containers |
| Container orchestrator | Provisions ephemeral Docker containers, mounts skills, enforces TTL |
| SSE relay | Passes container stdout/output through to the frontend as SSE events |
| Admin panel | SQLAdmin for managing installations, credentials, viewing sessions |
| Auth | GitHub OAuth, JWT tokens, refresh flow |

## Data Architecture

- PostgreSQL 16 (see [Data Models](./data-models-api.md))
- All tables share `id` (UUID PK), `created_at`, `updated_at` from `Base`
- BYOK credentials encrypted at rest with Fernet
- GitHub OAuth tokens encrypted at rest with Fernet

## API Design

- Endpoints under `/api/v1` (see [API Contracts](./api-contracts-api.md))
- JWT Bearer auth (15-min access, 7-day refresh cookie)
- SSE streaming for container output relay
- Rate limiting per-IP via SlowAPI
- Webhook ingestion with HMAC signature verification

## Testing Strategy

- `AsyncClient` + `ASGITransport` -- no real server needed
- Real Postgres in CI (service container)
- `conftest.py` sets env vars before imports (critical ordering)
- `asyncio_mode = "auto"` -- no explicit async markers needed

## Key Design Decisions

1. **No AI in the backend**: all AI logic runs inside ephemeral containers
2. **BYOK model**: each installation provides their own Claude credentials
3. **SSE passthrough**: backend relays container output, does not generate AI responses
4. **Flat modules only**: all modules use the simple flat pattern (router/service/models/schemas)
5. **Background webhook processing**: raw events persisted first, dispatched async with retry
