# Integration Architecture

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Overview

helPRs is a monorepo with 3 parts that communicate through well-defined integration points. The frontend (web) communicates with the backend (api) via REST + SSE. The backend integrates with GitHub and Anthropic APIs. Infrastructure orchestrates everything via Docker.

## Integration Points

```
┌──────────────┐     REST + SSE      ┌──────────────┐     Webhooks     ┌──────────────┐
│              │ ──────────────────→  │              │ ←────────────── │              │
│   Frontend   │     (12 endpoints)  │   Backend    │     (6 events)  │   GitHub     │
│   (web)      │ ←──────────────────  │   (api)      │ ──────────────→ │   API        │
│              │     JSON + SSE      │              │   REST (httpx)  │              │
└──────────────┘                     └──────┬───────┘                 └──────────────┘
                                           │
                                    ┌──────┴───────┐
                                    │              │
                                    │  PostgreSQL  │
                                    │  (db)        │
                                    │              │
                                    └──────┬───────┘
                                           │
                                    ┌──────┴───────┐
                                    │  Anthropic   │
                                    │  Claude API  │
                                    │  (via BYOK)  │
                                    └──────────────┘
```

## Web -> API Communication

### Transport

| Protocol | Use Case | Auth Mechanism |
|----------|----------|---------------|
| REST (JSON) | CRUD operations, auth, reports, feedback | `Authorization: Bearer {JWT}` header |
| SSE (EventSource) | Question streaming (`GET /stream`) | `?access_token={JWT}` query param (EventSource limitation) |
| SSE (fetch ReadableStream) | Feedback streaming (`POST /answers`) | `Authorization: Bearer {JWT}` header |

### Endpoints Used by Frontend

| Method | Endpoint | Feature Module | Purpose |
|--------|----------|---------------|---------|
| GET | `/api/v1/auth/github` | auth | Initiate OAuth (redirect) |
| GET | `/api/v1/auth/me` | auth | Fetch user profile |
| POST | `/api/v1/auth/refresh` | shared (apiFetch) | Silent JWT refresh |
| GET | `/api/v1/installations/:id` | installation | Fetch installation details |
| POST | `/api/v1/installations/:id/byok` | installation | Submit/update BYOK key |
| DELETE | `/api/v1/installations/:id/byok` | installation | Remove BYOK key |
| PUT | `/api/v1/installations/:id/suppression-labels` | installation | Save labels |
| GET | `/api/v1/sessions/:id` | session | Fetch session data (React Query) |
| GET | `/api/v1/sessions/:id/stream` | session | SSE question streaming |
| POST | `/api/v1/sessions/:id/answers` | session | Submit answer, SSE feedback |
| POST | `/api/v1/sessions/:id/questions/:num/report` | session | Report a question |
| POST | `/api/v1/sessions/:id/feedback` | session | Submit session feedback |

### Auth Flow

```
Frontend                          Backend                        GitHub
   │                                │                              │
   ├─── redirect ──────────────────→│                              │
   │    GET /auth/github             │── redirect ────────────────→│
   │                                │   (CSRF state cookie)        │
   │                                │←── callback with code ──────│
   │←── redirect with access_token ─│                              │
   │    + refresh_token cookie       │                              │
   │                                │                              │
   ├─── GET /auth/me ──────────────→│                              │
   │←── UserResponse ──────────────│                              │
```

### Token Refresh Flow

```
Frontend (apiFetch)               Backend
   │                                │
   ├─── any request ───────────────→│
   │←── 401 Unauthorized ──────────│
   │                                │
   ├─── POST /auth/refresh ────────→│  (reads refresh_token cookie)
   │←── new access_token ──────────│
   │                                │
   ├─── retry original request ────→│
   │←── success ───────────────────│
```

## API -> External Services

### GitHub API Integration

| Service | Protocol | Purpose |
|---------|----------|---------|
| GitHub OAuth | REST (httpx) | Token exchange, user profile fetch |
| GitHub REST API | REST (httpx) | Org membership checks, PR diff fetch |
| GitHub Webhooks | Inbound POST | Installation events, PR events |

**Diff fetching**: Streaming with 1MB cap. Large PRs (>=2000 lines) ranked by file change size, trimmed to 40K-line budget.

### Anthropic Claude API

| Service | Protocol | Purpose |
|---------|----------|---------|
| Anthropic API | REST via Pydantic AI | Question generation, feedback generation, scoring |

**BYOK model**: Each user's own API key (Fernet-encrypted at rest). Fresh `Agent` per invocation -- zero caching.

## API -> Database

| Integration | Driver | Pool Config |
|-------------|--------|------------|
| PostgreSQL | asyncpg (via SQLAlchemy async) | pool_size=20, max_overflow=10 |

**Pattern**: DB phase / HTTP phase split -- handlers load from DB and snapshot results, then close DB scope before making outbound HTTP calls.

## Infrastructure Orchestration

### Local Development

```
docker-compose.yml
├── api (dev target) ── volume mounts src/ ── hot-reload (uvicorn --reload)
├── web (dev target) ── volume mounts src/ ── hot-reload (Vite HMR)
└── db (postgres:16-alpine) ── pgdata volume ── health check
```

### Production

```
docker-compose.prod.yml (Coolify)
├── api (production target) ── env_file: .env ── restart: unless-stopped
├── web (production target) ── nginx:alpine ── SPA + asset caching
└── db (postgres:16-alpine) ── pgdata volume ── restart: unless-stopped
```

### CI/CD Flow

```
Push to any branch → ci.yml → lint + test (4 parallel jobs) → build (gated)
Push to main → deploy.yml → build + push to GHCR → POST Coolify webhook
```
