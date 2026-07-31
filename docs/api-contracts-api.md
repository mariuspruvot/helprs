# API Contracts

REST reference for the helPRs API. All endpoints under `/api/v1/*` require auth unless noted. Pydantic schemas are defined in `apps/api/src/helprs/modules/*/schemas.py`; see [data-models-api.md](data-models-api.md) for the field details.

**Conventions**

- Base path: `/api/v1`
- Unauthenticated endpoints return `401 Unauthorized` when a bearer token is missing or invalid. Installation/session access failures return `403 Forbidden`.
- Rate limiting is applied per route (via `slowapi`). Limits are shown inline below.
- `{installation_id}` in paths is the **GitHub installation ID** (integer), not the internal UUID.
- Session IDs are UUIDs.

## Health

### `GET /health`

Unauthenticated liveness probe that also checks DB reachability.

- **200** `{"status": "ok", "db": "ok"}` — API + DB healthy.
- **503** `{"status": "degraded", "db": "unreachable"}` — API up, DB unreachable.

## Auth — `/api/v1/auth/*`

### `GET /auth/github`

Redirects to GitHub OAuth (`github.com/login/oauth/authorize`). Sets an httpOnly `oauth_state` cookie for CSRF (10 min TTL). Scopes requested: `read:user user:email read:org`.

- **302** redirect to GitHub.
- Rate limit: 10/min.

### `GET /auth/github/callback`

Handles two entry flows: OAuth login (with `state`) and GitHub App install (with `installation_id` + `setup_action`, no `state`).

Query params: `code` (required), `state` (OAuth flow), `installation_id` + `setup_action` (install flow).

On success: creates/updates the user, issues an access token, sets an httpOnly `refresh_token` cookie (7 days), and redirects to `{APP_BASE_URL}/auth/callback?access_token=...`.

- **302** redirect on success.
- **401** on missing/invalid `state`.
- Rate limit: 10/min.

### `POST /auth/refresh`

Rotates the access token using the `refresh_token` httpOnly cookie. Writes a new `refresh_token` cookie on the response.

- **200** `TokenResponse { access_token, token_type: "bearer" }`.
- **401** if the refresh cookie is missing or invalid.
- Rate limit: 10/min.

### `GET /auth/me`

Requires auth. Returns the authenticated user.

- **200** `UserResponse`.
- Rate limit: 30/min.

### `GET /auth/me/stats`

Requires auth. Returns aggregated session statistics for the user.

- **200** `UserStatsResponse { daily_counts: [...], totals: {...} }`.
- Rate limit: 30/min.

### `POST /auth/logout`

Clears the `refresh_token` cookie.

- **200** `{"status": "ok"}`.

## Installations — `/api/v1/installations/*`

All endpoints require auth. Admin endpoints additionally call `verify_admin_permission`.

### `GET /installations`

List installations the user has access to (owns, or org member).

- **200** `InstallationListResponse { items: InstallationResponse[], total }`. Each item includes `session_count`, BYOK status, suppression labels, and `post_results_to_pr`.
- Rate limit: 30/min.

### `GET /installations/{installation_id}`

Installation detail — requires admin permission on the installation.

- **200** `InstallationDetailResponse`.
- **404** if unknown.
- Rate limit: 30/min.

### `POST /installations/{installation_id}/byok`

Configure the BYOK Claude credential. Accepts API keys (`sk-ant-api03-...`) and OAuth tokens (`sk-ant-oat...`). OAuth tokens skip server-side validation.

- Request: `BYOKConfigureRequest { api_key }`.
- **200** `BYOKConfigResponse`.
- **404** if installation unknown.
- Rate limit: 10/min.

### `DELETE /installations/{installation_id}/byok`

Remove the BYOK credential.

- **204** No Content.
- **404** if installation unknown.
- Rate limit: 10/min.

### `PUT /installations/{installation_id}/suppression-labels`

Update the list of PR labels that cause helPRs to skip session creation (matched case-insensitively when a PR is opened).

- Request: `SuppressionLabelsRequest { labels: string[] }`.
- **200** `SuppressionLabelsResponse { labels }`.
- Rate limit: 10/min.

### `GET /installations/{installation_id}/sessions`

Paginated session history for an installation.

- Query params: `page` (default 1), `per_page` (default 20, max 100), `status` (optional filter).
- **200** `PaginatedSessionsResponse { items, total, page, per_page, total_pages }`.
- Rate limit: 30/min.

### `PUT /installations/{installation_id}/post-results`

Enable or disable automatic posting of challenge-me score cards to PRs.

- Request: `PostResultsSettingRequest { post_results_to_pr: boolean }`.
- **200** `PostResultsSettingResponse { post_results_to_pr }`.
- Rate limit: 10/min.

## Webhooks — `/api/v1/webhooks/*`

### `POST /webhooks/github`

Unauthenticated but HMAC-verified via the `X-Hub-Signature-256` header (shared secret `GITHUB_WEBHOOK_SECRET`). Required header: `X-GitHub-Delivery`.

Flow: verify HMAC → persist raw event → return 200 → dispatch processing as a background task. Duplicate deliveries (same `X-GitHub-Delivery`) are idempotent.

- **200** `{"status": "ok", "duplicate": false|true}`.
- **400** on missing `X-GitHub-Delivery`, invalid JSON, or HMAC failure.
- Handled events: `installation.*`, `pull_request.opened`, `pull_request.synchronize`. Other events are logged and ignored (still stored for audit).
- Rate limit: 100/min.

## Container sessions — `/api/v1/containers/*`

All endpoints require auth. Installation access is checked at session creation; session-level access (`verify_session_access`) is checked on all other routes.

### `POST /containers/sessions`

Create a session record and start a Claude runner container for a given PR + skill.

- Request: `CreateSessionRequest { installation_id, pr_number, repo_full_name: "owner/repo", skill_name }`.
- **201** `ContainerSessionResponse`.
- **404** if the installation is unknown or has no BYOK configured.
- Rate limit: 10/min.

### `GET /containers/sessions/{session_id}`

Current session status and metadata.

- **200** `ContainerSessionResponse`.
- Rate limit: 30/min.

### `GET /containers/sessions/{session_id}/stream`

SSE stream of live container output (while `status = RUNNING`).

- Query param: `offset` (default 0) — number of events to skip, for client-side resume. Also read from `Last-Event-ID` header (set automatically by `EventSource` on reconnect).
- **200** `text/event-stream`. Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- **404** if the container is not running.
- Each event is a line-delimited SSE message carrying a stream-json object. On stream end, a final `event: done` carries `{"message": "...", "status": "completed" | "failed"}`.
- Rate limit: 60/min.

### `GET /containers/sessions/{session_id}/events`

Persisted stream-json events (JSONB) for replay without SSE. Suitable for rendering completed sessions.

- **200** `SessionEventsListResponse { session_id, events: SessionEventResponse[], total }`, ordered by `event_id`.
- Rate limit: 30/min.

### `GET /containers/sessions/{session_id}/scorecard`

Parsed score card for a completed session (currently only emitted by the `challenge-me` skill).

- **200** `ScorecardResponse { session_id, scorecard, xp_earned }`. `scorecard` is `null` if none was extracted.
- Rate limit: 30/min.

### `POST /containers/sessions/{session_id}/message`

Send a follow-up message to a running container. Delivered to the container's Claude CLI stdin via a FIFO (`docker exec`).

- Request: `SendMessageRequest { content }`.
- **200** `SendMessageResponse { session_id, status: "sent", message }`.
- Rate limit: 30/min.

### `POST /containers/sessions/{session_id}/stop`

Stop a running container (graceful SIGTERM then kill). Marks the session as `COMPLETED` or `FAILED`.

- **200** `StopSessionResponse { id, status, message }`.
- Rate limit: 10/min.

### `DELETE /containers/sessions/{session_id}`

Delete a session and its persisted events.

- **200** `{"status": "deleted", "id": "..."}`.
- Rate limit: 10/min.

## Admin — `/admin`

SQLAdmin panel mounted at `/admin`. Not part of the REST contract; see `admin/views.py` for the exposed models. Credentials:

- **Development**: any password (auto-auth).
- **Production**: the `ADMIN_PASSWORD` env var.
