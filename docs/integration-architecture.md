# Integration Architecture

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Overview

helPRs is a monorepo with 3 parts that communicate through 4 integration points. Post-pivot, AI execution happens inside ephemeral Docker containers -- the backend acts as an orchestrator, not an AI host.

```
+-------------------------------------------------------------+
|                        GitHub.com                            |
|  +--------------+  +--------------+  +--------------------+  |
|  |  OAuth API   |  |  REST API    |  |  Webhooks          |  |
|  |  (user auth) |  |  (comments)  |  |  (install, PR      |  |
|  |              |  |              |  |   events)           |  |
|  +------+-------+  +------+-------+  +--------+-----------+  |
+---------+------------------+-------------------+-------------+
          |                  |                   |
          v                  v                   v
+-------------------------------------------------------------+
|                    API (FastAPI :8000)                        |
|  +----------+  +---------------+  +------------------------+ |
|  | Identity  |  | Container     |  | Webhook                | |
|  | Module    |  | Module        |  | Module                 | |
|  |           |  |               |  |                        | |
|  | OAuth     |  | Orchestrate   |  | HMAC verify            | |
|  | JWT       |  | SSE relay     |  | Event dispatch         | |
|  | Refresh   |  | Lifecycle     |  | Session creation       | |
|  +----------+  +-------+-------+  +------------------------+ |
|                         |                                    |
|         +---------------+--+                                 |
|         | Docker Socket    |                                 |
|         +-------+----------+                                 |
|                 |                                            |
|         +-------v----------+                                 |
|         | Ephemeral         |                                |
|         | Claude Runner     |                                |
|         | Container         |                                |
|         |                   |                                |
|         | - Claude Code CLI |                                |
|         | - gh pr checkout  |                                |
|         | - Skill execution |                                |
|         | - Output stream   |                                |
|         +-------------------+                                |
|                                                              |
|  +--------------------------------------------------------+  |
|  |              PostgreSQL :5432                           |  |
|  |  github_users | installations | webhook_events         |  |
|  |  byok_configs | container_sessions (Phase 2)           |  |
|  +--------------------------------------------------------+  |
+------------------------------+-------------------------------+
                               |
                               | REST + SSE
                               v
+-------------------------------------------------------------+
|                    Web (React :5173)                          |
|  +----------+  +---------------+  +------------------------+ |
|  | Auth      |  | Session       |  | Dashboard /            | |
|  | Feature   |  | Feature       |  | Installation           | |
|  |           |  |               |  | Features               | |
|  | OAuth     |  | SSE stream    |  |                        | |
|  | callback  |  | (container    |  | Credential config      | |
|  | JWT       |  |  output)      |  | Label management       | |
|  +----------+  +---------------+  +------------------------+ |
+-------------------------------------------------------------+
```

## Integration Points

### 1. Web -> API (REST + SSE)

| Type | Protocol | Details |
|------|----------|---------|
| REST | HTTP/JSON | Endpoints under `/api/v1` |
| SSE | `text/event-stream` | Container output relay stream |
| Auth | JWT Bearer | 15-min access tokens, 7-day refresh cookies |

**Data flow:**

```
Web                              API
 |                                |
 +-- GET /auth/github ----------> | (302 -> GitHub OAuth)
 |<-- GET /auth/callback --------| (302 + JWT + refresh cookie)
 |                                |
 +-- GET /installations --------> |
 +-- POST /.../byok ------------> | (validates + stores credentials)
 +-- PUT /.../suppression-labels->|
 |                                |
 +-- POST /sessions/:id/run ----> | (triggers container, Coming in Phase 2)
 +-- SSE /sessions/:id/stream --> | (container output relay, Coming in Phase 2)
```

**Client implementation:** `apiFetch` wrapper in `shared/api/client.ts`:

- Automatic `Authorization: Bearer` header from Zustand auth store
- 401 retry with `POST /auth/refresh` (httpOnly cookie)
- Force re-auth redirect on refresh failure
- `credentials: 'include'` on all requests

### 2. API -> GitHub (REST + Webhooks)

| Type | Direction | Details |
|------|-----------|---------|
| REST (outbound) | API -> GitHub | OAuth token exchange, PR comments |
| Webhooks (inbound) | GitHub -> API | Installation + PR events via HMAC-signed POST |

**Outbound calls:**

| Call | When | Auth |
|------|------|------|
| `POST /login/oauth/access_token` | OAuth callback | Client ID + secret |
| `GET /user` | After OAuth | User access token |
| `POST /repos/{owner}/{repo}/issues/{pr}/comments` | PR opened | Installation token |

**Inbound webhooks:**

| Event | Action | Handler |
|-------|--------|---------|
| `installation.created` | Create installation record | `handle_installation_created` |
| `installation.deleted` | Soft-delete installation | `handle_installation_deleted` |
| `installation.suspended` | Mark suspended | `handle_installation_suspended` |
| `installation.unsuspended` | Clear suspension | `handle_installation_unsuspended` |
| `pull_request.opened` | Post PR comment with session link | `handle_pull_request_opened` |
| `pull_request.synchronize` | Update session or create if missing | `handle_pull_request_synchronize` |

**Webhook processing pipeline:**

1. HMAC SHA-256 signature verification (`X-Hub-Signature-256`)
2. Duplicate detection via `delivery_id`
3. Raw event persisted to `webhook_events` table
4. Background task dispatches to event-specific handler
5. Status machine: `pending` -> `processing` -> `processed` | `failed` -> `abandoned` (after 5 retries)

### 3. API -> Ephemeral Container (Docker SDK)

| Type | Protocol | Details |
|------|----------|---------|
| Container lifecycle | Docker SDK | Provision, start, stream, destroy |
| Credential injection | Env vars | `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, repo/PR metadata |
| Skill mounting | Docker volume | Skill definitions from `skills/` directory |
| Output capture | stdout/SSE | Container output relayed to frontend |

**Container lifecycle:**

1. API receives trigger (webhook auto-trigger or user-initiated)
2. Retrieves installation's Claude credentials from DB (Fernet-decrypted)
3. Provisions ephemeral `claude-runner` container with:
   - Credentials as env vars (never persisted in container)
   - Skill folder mounted as volume
   - Repo/PR metadata as env vars
4. Container executes: `gh repo clone --depth=1` + `gh pr checkout` + skill
5. Output streamed back to API
6. Container destroyed after completion or TTL timeout

### 4. API -> PostgreSQL (asyncpg)

| Type | Protocol | Details |
|------|----------|---------|
| Database | PostgreSQL 16 via asyncpg | Async connection pool via SQLAlchemy |
| ORM | SQLAlchemy 2.0 async | `async_sessionmaker` with `AsyncSession` |
| Migrations | Alembic | Auto-run on container start |

**Connection management:**

- Engine created in app lifespan (`create_app()`)
- `async_sessionmaker` injected via `get_db` dependency
- Connection string: `postgresql+asyncpg://...`

## Cross-Part Data Flow: Container Skill Execution

```
1. GitHub webhook: pull_request.opened
   +-> API: webhook module verifies HMAC, persists event
       +-> API: handler posts PR comment with session link

2. User clicks session link (or auto-trigger fires)
   +-> Web: ProtectedRoute checks auth
       +-> Web: redirects to GitHub OAuth (if needed)
           +-> API: exchanges code for tokens, returns JWT
               +-> Web: stores JWT, navigates to session page

3. Skill execution triggered
   +-> API: container module retrieves Claude credentials
       +-> API: provisions ephemeral claude-runner container
           +-> Container: gh repo clone --depth=1 + gh pr checkout
               +-> Container: loads assigned skill
                   +-> Container: Claude Code executes skill against PR
                       +-> Container: streams output -> API (SSE relay)
                           +-> Web: renders results in real-time

4. Container completes
   +-> API: captures exit status, destroys container
       +-> API: records session result
```

## Security Boundaries

| Boundary | Mechanism |
|----------|-----------|
| Web -> API | JWT Bearer tokens (15-min expiry) |
| API -> GitHub | Installation JWT tokens (10-min expiry, signed with RSA private key) |
| GitHub -> API | HMAC SHA-256 webhook signatures |
| API -> Container | Ephemeral env vars (credentials never persisted in container filesystem) |
| API -> PostgreSQL | Connection string credentials |
| Credential storage | Fernet encryption at rest in `byok_configs` table |
| Container isolation | Ephemeral lifecycle, destroyed after use, resource limits (CPU/memory/TTL) |
