# API Contracts — Backend (api)

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

All routes are prefixed with `/api/v1`. The admin panel is mounted at `/admin`. A bare `/health` endpoint sits outside the prefix.

---

## Health

| Method | Path | Handler | Auth | Request | Response |
|--------|------|---------|------|---------|----------|
| GET | `/health` | `health_check` | None | -- | `{"status": "ok"}` |

---

## Auth (`/api/v1/auth`)

| Method | Path | Handler | Auth | Rate Limit | Request | Response |
|--------|------|---------|------|------------|---------|----------|
| GET | `/auth/github` | `github_login` | None | 10/min | -- | 302 redirect to GitHub OAuth |
| GET | `/auth/github/callback` | `github_callback` | None (CSRF state cookie) | 10/min | `?code=&state=` | 302 redirect to frontend with `access_token` query param; sets `refresh_token` httpOnly cookie |
| POST | `/auth/refresh` | `refresh` | httpOnly `refresh_token` cookie | 10/min | -- | `TokenResponse {access_token, token_type}` |
| GET | `/auth/me` | `get_me` | Bearer JWT | 30/min | -- | `UserResponse {id, github_id, github_login, email, avatar_url, created_at}` |
| POST | `/auth/logout` | `logout` | None | -- | -- | `{"status":"ok"}`; clears `refresh_token` cookie |

---

## Installations (`/api/v1/installations`)

| Method | Path | Handler | Auth | Rate Limit | Request | Response |
|--------|------|---------|------|------------|---------|----------|
| GET | `/installations` | `list_installations` | Bearer JWT | 30/min | -- | `InstallationListResponse {items[], total}` |
| GET | `/installations/{installation_id}` | `get_installation` | Bearer JWT + admin permission | 30/min | -- | `InstallationDetailResponse` |
| POST | `/installations/{installation_id}/byok` | `post_byok` | Bearer JWT + admin permission | 10/min | `BYOKConfigureRequest {api_key}` (must start with `sk-ant-`) | `BYOKConfigResponse {key_hint, key_status, validated_at}` |
| DELETE | `/installations/{installation_id}/byok` | `delete_byok` | Bearer JWT + admin permission | 10/min | -- | 204 No Content |
| PUT | `/installations/{installation_id}/suppression-labels` | `put_suppression_labels` | Bearer JWT + admin permission | 10/min | `SuppressionLabelsRequest {labels[]}` (max 20, alphanumeric+hyphens, max 50 chars each) | `SuppressionLabelsResponse {labels[]}` |

> `installation_id` in the path is the **GitHub installation ID** (int), not the internal UUID.

---

## Webhooks (`/api/v1/webhooks`)

| Method | Path | Handler | Auth | Rate Limit | Request | Response |
|--------|------|---------|------|------------|---------|----------|
| POST | `/webhooks/github` | `receive_github_webhook` | HMAC SHA-256 (`X-Hub-Signature-256`) | 100/min | Raw JSON body (GitHub webhook payload) | `{"status": "ok", "duplicate": bool}` |

**Dispatched event types:** `installation.created`, `installation.deleted`, `installation.suspended`, `installation.unsuspended`, `pull_request.opened`, `pull_request.synchronize`.

---

## Sessions (`/api/v1/sessions`)

### REST Endpoints

| Method | Path | Handler | Auth | Rate Limit | Request | Response |
|--------|------|---------|------|------------|---------|----------|
| GET | `/sessions/{session_id}` | `get_session` | Bearer JWT (installation access verified) | 60/min | -- | `SessionResponse` (includes live diff from GitHub, progress, score, feedback) |
| POST | `/sessions/{session_id}/questions/{question_number}/report` | `report_question` | Bearer JWT | 30/min | `QuestionReportRequest {reason}` (enum: irrelevant, factually_incorrect, ambiguous, too_easy, too_hard, other) | 201 `QuestionReportResponse`. 409 if already reported. |
| POST | `/sessions/{session_id}/feedback` | `submit_feedback` | Bearer JWT | 10/min | `SessionFeedbackRequest {rating: bool, comment?: str}` (max 2000 chars) | 201 `SessionFeedbackResponse`. 409 if already submitted. Session must be COMPLETED. |

### SSE Streaming Endpoints

| Method | Path | Handler | Auth | Rate Limit | Response Type |
|--------|------|---------|------|------------|---------------|
| GET | `/sessions/{session_id}/stream` | `stream_session` | Bearer JWT (also accepts `?access_token=`) | 20/min | `text/event-stream` |
| POST | `/sessions/{session_id}/answers` | `submit_answer` | Bearer JWT | 60/min | `text/event-stream` |

**GET /stream SSE events:**

| Event | Payload | Description |
|-------|---------|-------------|
| `question_token` | `{question_id, token, number, total}` | Streaming delta |
| `question` | `{question_id, text, number, total, file_refs}` | Complete question |
| `scoring` | `{text}` | Scoring phase started |
| `score` | `{depth, accuracy, completeness, insight, verdict, gaps}` | Final score |
| `done` | `{session_id, question_count}` | Session complete |
| `error` | `{error, message, retryable}` | LLM/timeout failure |

**POST /answers:**

- **Request:** `SubmitAnswerRequest {question_number: int, text: str}` (1-8000 chars)
- **SSE events:** `feedback_token`, `feedback`, `done`, `error`

---

## Admin Panel (`/admin`)

SQLAdmin UI with password-based auth (`ADMIN_PASSWORD` env var; auto-login in development).

- **Read-only views:** WebhookEvents, Sessions
- **Editable views:** GitHubUsers, Installations, BYOKConfigs
