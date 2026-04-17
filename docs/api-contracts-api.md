# API Contracts -- Backend

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Overview

- Base prefix: `/api/v1`
- Auth mechanism: JWT Bearer tokens (HS256). Access tokens (15 min) issued after GitHub OAuth. Refresh tokens (7 days) stored as httpOnly cookies.
- Rate limiting: SlowAPI (per-IP via `get_remote_address`)
- Error format: `{"error": "<error_code>", "message": "<text>", "detail": <any>}`
- Webhook auth: HMAC SHA-256 signature verification via `X-Hub-Signature-256` header

## Route Groups

### Health -- /health

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| GET | `/health` | None | None | Health check |

#### GET /health

- Response: `{"status": "ok"}`
- Notes: Mounted directly on the app, not under `/api/v1`

---

### Auth -- /api/v1/auth

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| GET | `/api/v1/auth/github` | None | 10/min | Redirect to GitHub OAuth |
| GET | `/api/v1/auth/github/callback` | None | 10/min | Handle OAuth callback |
| POST | `/api/v1/auth/refresh` | Refresh cookie | 10/min | Refresh access token |
| GET | `/api/v1/auth/me` | Bearer JWT | 30/min | Get current user |
| POST | `/api/v1/auth/logout` | None | None | Clear refresh cookie |

#### GET /api/v1/auth/github

- Response: 302 redirect to `https://github.com/login/oauth/authorize`
- Sets `oauth_state` cookie (httpOnly, samesite=lax, 600s max-age)

#### GET /api/v1/auth/github/callback

- Query params: `code` (required), `state` (required)
- Response: 302 redirect to `{frontend_url}/auth/callback?access_token={jwt}`
- Sets `refresh_token` cookie (httpOnly, 7-day max-age)

#### POST /api/v1/auth/refresh

- Auth: `refresh_token` httpOnly cookie
- Response: `TokenResponse { access_token, token_type }`

#### GET /api/v1/auth/me

- Auth: Bearer JWT
- Response: `UserResponse { id, github_id, github_login, email, avatar_url, created_at }`

#### POST /api/v1/auth/logout

- Response: `{"status": "ok"}`
- Deletes `refresh_token` cookie

---

### Installations -- /api/v1/installations

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| GET | `/api/v1/installations` | Bearer JWT | 30/min | List accessible installations |
| GET | `/api/v1/installations/{installation_id}` | Bearer JWT | 30/min | Get installation detail |
| POST | `/api/v1/installations/{installation_id}/byok` | Bearer JWT | 10/min | Configure credentials |
| DELETE | `/api/v1/installations/{installation_id}/byok` | Bearer JWT | 10/min | Remove credentials |
| PUT | `/api/v1/installations/{installation_id}/suppression-labels` | Bearer JWT | 10/min | Update suppression labels |

**Path params:** `installation_id` is the **GitHub installation ID** (integer), not the internal UUID.

#### GET /api/v1/installations

- Response: `InstallationListResponse { items: InstallationResponse[], total: int }`

#### POST /api/v1/installations/{installation_id}/byok

- Request: `BYOKConfigureRequest { api_key: str }` -- Claude credentials, min 20 chars
- Response: `BYOKConfigResponse { key_hint, key_status, validated_at }`
- Notes: Key is Fernet-encrypted at rest.

#### DELETE /api/v1/installations/{installation_id}/byok

- Response: 204 No Content

#### PUT /api/v1/installations/{installation_id}/suppression-labels

- Request: `SuppressionLabelsRequest { labels: list[str] }` -- max 20 items
- Response: `SuppressionLabelsResponse { labels: list[str] }`

---

### Webhooks -- /api/v1/webhooks

| Method | Path | Auth | Rate Limit | Description |
|--------|------|------|------------|-------------|
| POST | `/api/v1/webhooks/github` | HMAC SHA-256 | 100/min | Receive GitHub webhooks |

#### POST /api/v1/webhooks/github

- Auth: `X-Hub-Signature-256` header
- Response: `{"status": "ok", "duplicate": false}`
- Handled events: `installation.*`, `pull_request.opened`, `pull_request.synchronize`

---

### Container Sessions -- Coming in Phase 2

Container session endpoints will be added when the container module is implemented. Expected endpoints:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/sessions/{id}/run` | Bearer JWT | Trigger skill execution in container |
| GET | `/api/v1/sessions/{id}/stream` | Bearer JWT | SSE stream of container output |
| GET | `/api/v1/sessions/{id}` | Bearer JWT | Get session status + results |

Exact schemas TBD.

---

### Admin -- /admin

- SQLAdmin panel at `/admin`
- Auth: session-based. Development mode accepts any login. Production requires `ADMIN_PASSWORD` env var.
- Full CRUD for: GitHubUser, Installation, BYOKConfig
- Read-only views for: WebhookEvent
- Sensitive fields excluded: `github_access_token_enc`, `encrypted_api_key`
