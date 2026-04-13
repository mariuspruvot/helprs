# Architecture — Backend (api)

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Executive Summary

FastAPI backend for **helPRs** -- a Socratic comprehension tool for pull requests. The API handles GitHub OAuth authentication, GitHub App webhook processing, BYOK (Bring Your Own Key) Anthropic API key management, and real-time AI-driven comprehension sessions streamed via SSE.

## Technology Stack

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| Framework | FastAPI | >= 0.115.0 | Async web framework |
| Language | Python | 3.12 | Runtime |
| ORM | SQLAlchemy (async) | >= 2.0.36 | Database access with asyncpg driver |
| Database | PostgreSQL | 16 | Primary data store |
| Migrations | Alembic | >= 1.14.0 | Schema versioning |
| LLM | Pydantic AI | >= 0.1.0 | Anthropic Claude integration |
| Auth | python-jose + Fernet | >= 3.3.0 | JWT tokens + symmetric encryption |
| HTTP Client | httpx | >= 0.28.0 | GitHub API, Anthropic validation |
| Logging | structlog | >= 24.4.0 | JSON structured logging |
| Monitoring | Sentry SDK | >= 2.19.0 | Error tracking (optional) |
| Rate Limiting | slowapi | >= 0.1.9 | Per-endpoint rate limiting |
| Admin | SQLAdmin | >= 0.20.0 | Admin panel UI |
| Package Manager | uv | latest | Fast Python package management |

## Architecture Pattern

**Hybrid architecture** with two module patterns:

1. **Simple modules** (identity, installation, webhook, billing): Flat `router.py` / `service.py` / `models.py` / `schemas.py` structure.
2. **Clean Architecture** (comprehension): Full hexagonal / ports-and-adapters with domain, application, infrastructure, and presentation layers.

## Module Structure

### Simple Modules

```
module/
  models.py      -- SQLAlchemy ORM models
  schemas.py     -- Pydantic request/response DTOs
  router.py      -- FastAPI route definitions
  service.py     -- Business logic
```

### Comprehension Module (Clean Architecture)

```
comprehension/
  domain/
    entities.py       -- Dataclass domain entities
    value_objects.py   -- StrEnum value objects
    interfaces.py      -- Protocol ports (SessionRepository, LLMProvider)
    services.py        -- Pure domain services
  application/
    commands.py        -- Command DTOs
    queries.py         -- Query/Result DTOs
    handlers.py        -- Use-case handlers (CQRS-lite)
  infrastructure/
    models.py          -- SQLAlchemy ORM models
    repositories.py    -- Repository implementation
    agents.py          -- LLM provider (Pydantic AI)
    github_diff.py     -- GitHub diff fetching (1MB cap)
    diff_refs.py       -- Diff parsing, file-ref extraction
  presentation/
    routers.py         -- REST endpoints
    sse.py             -- SSE streaming endpoints
    schemas.py         -- Response schemas
    dependencies.py    -- DI factories
    answer_pubsub.py   -- In-process text registry
```

## Entry Point & App Factory

`helprs.main:create_app()` is the app factory. The lifespan manager:

1. Creates async SQLAlchemy engine (asyncpg, pool_size=20, max_overflow=10)
2. Creates session factory on `app.state`
3. Registers global `get_db_context` for out-of-request-scope DB access
4. Sets up SQLAdmin at `/admin`
5. Runs webhook crash-replay (re-dispatches stuck events)
6. Starts periodic webhook reaper task (every 5 minutes)
7. On shutdown: cancels reaper, awaits in-flight tasks, disposes engine

## Authentication & Security

### OAuth Flow

1. `GET /auth/github` -> redirect to GitHub (`read:user,user:email,read:org` scopes)
2. GitHub callback -> exchange code -> upsert user -> issue JWT pair
3. **Access token**: HS256, 15-min TTL, passed via redirect URL query param
4. **Refresh token**: HS256, 7-day TTL, httpOnly cookie

### Authorization Model

- **User access**: JWT Bearer header (or `?access_token=` query param for SSE)
- **Installation access**: Verified via GitHub user orgs membership
- **Admin permission**: Owner (User) or admin member (Org) check via GitHub API

### Encryption

- **Fernet symmetric encryption** for GitHub access tokens and BYOK Anthropic API keys
- **BYOK zero-retention**: Decrypted keys are ephemeral, dropped at function exit
- **Hash-only persistence**: Question and answer text stored as SHA-256 hashes only

### Middleware Chain

1. CORS (configurable origins, credentials allowed)
2. Request logging (structlog, request_id binding, timing, X-Request-ID header)
3. Rate limiting (slowapi, per-endpoint limits)

## Key Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| Hash-only persistence | Privacy: no verbatim user content in DB (FR35/NFR14) |
| Fresh Agent per LLM call | Zero key caching, zero retention for BYOK security |
| DB phase / HTTP phase split | Avoid holding DB connections during long outbound I/O |
| Unit of Work pattern | Repositories flush but never commit; caller owns transaction |
| Webhook durability | Persist-first, process-async with crash-replay and periodic reaper |
| Manual SSE framing | No `sse-starlette` dependency; full control over streaming protocol |
| Large PR handling | Diffs >= 2000 lines ranked and trimmed to 40K-line budget |

## Dependency Injection

| Dependency | Scope | Purpose |
|------------|-------|---------|
| `GetSettings` | Singleton (cached) | Application configuration |
| `DbSession` | Request-scoped | SQLAlchemy async session |
| `get_current_user` | Request-scoped | JWT validation + user lookup |
| `get_llm_provider` | Request-scoped | Fresh PydanticAI LLM provider |
| `verify_webhook_signature` | Request-scoped | HMAC verification |

## Observability

- **Structured logging**: structlog with JSON renderer, ISO timestamps
- **Sentry**: Optional (`SENTRY_DSN`), 20% trace sample rate, FastAPI + Starlette + Asyncio integrations
- **Request IDs**: Bound to every log entry, returned in `X-Request-ID` header

## Known Technical Debt

- Access check is installation-level, not repository-level (security concern for `repository_selection="selected"`)
- `types` Makefile target (OpenAPI -> TypeScript) is a placeholder
