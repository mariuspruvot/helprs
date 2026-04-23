# Data Models

Database schema and Pydantic API schemas. Models live in `apps/api/src/helprs/modules/*/models.py`; schemas in `apps/api/src/helprs/modules/*/schemas.py`. See [api-contracts-api.md](api-contracts-api.md) for which endpoints return which schemas.

## Base columns

All tables inherit from `Base`, which provides:

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| `id` | UUID | PK | `uuid4()` | Primary key |
| `created_at` | DateTime(tz) | NOT NULL | `now()` | Row creation time |
| `updated_at` | DateTime(tz) | NOT NULL | `now()` (onupdate: `now()`) | Last modification time |

## Tables

### `github_users`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `github_id` | BigInteger | UNIQUE, NOT NULL, INDEX | GitHub numeric user ID |
| `github_login` | String(255) | NOT NULL, INDEX | GitHub username |
| `email` | String(255) | nullable | Email address |
| `avatar_url` | String(512) | nullable | GitHub avatar URL |
| `github_access_token_enc` | String(512) | NOT NULL | Fernet-encrypted GitHub OAuth token |

### `installations`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `github_installation_id` | BigInteger | UNIQUE, NOT NULL, INDEX | GitHub App installation ID |
| `account_login` | String(255) | NOT NULL | Account name (user / org) |
| `account_id` | BigInteger | NOT NULL | GitHub account numeric ID |
| `account_type` | String(50) | NOT NULL | `"User"` or `"Organization"` |
| `repository_selection` | String(20) | NOT NULL | `"all"` or `"selected"` |
| `app_slug` | String(255) | NOT NULL | GitHub App slug |
| `target_type` | String(50) | NOT NULL | `"Organization"` or `"User"` |
| `permissions` | JSON | nullable | GitHub App permissions granted |
| `events` | JSON | nullable | Subscribed webhook events |
| `suppression_labels` | JSON | nullable (default `[]`) | PR labels that suppress session creation |
| `post_results_to_pr` | Boolean | NOT NULL, default `false` | Whether session score cards are posted as PR comments |
| `suspended_at` | DateTime(tz) | nullable | When the installation was suspended |
| `deleted_at` | DateTime(tz) | nullable | Soft-delete timestamp |

Relationships: `byok_config` — one-to-one with `byok_configs`.

### `byok_configs`

Fernet-encrypted Claude credentials per installation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `installation_id` | UUID | FK(installations.id), UNIQUE, NOT NULL, INDEX | Parent installation |
| `encrypted_api_key` | String(1024) | NOT NULL | Fernet-encrypted credentials |
| `key_status` | String(20) | default `"valid"` | Validation status |
| `validated_at` | DateTime(tz) | nullable | Last validation timestamp |
| `key_hint` | String(20) | nullable | Last-4 hint (`"...xxxx"`) |

### `webhook_events`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `delivery_id` | String(64) | UNIQUE, NOT NULL, INDEX | `X-GitHub-Delivery` header |
| `event_type` | String(50) | NOT NULL, INDEX | `X-GitHub-Event` header value |
| `action` | String(50) | nullable | Payload `action` field |
| `github_installation_id` | BigInteger | nullable, INDEX | Extracted installation ID |
| `payload` | JSONB | NOT NULL | Raw webhook JSON payload |
| `status` | String(20) | NOT NULL, default `"pending"`, INDEX | `pending` / `processing` / `processed` / `failed` / `ignored` / `abandoned` |
| `retry_count` | Integer | NOT NULL, default `0` | Processing attempts |
| `error_message` | Text | nullable | Last error message |
| `processed_at` | DateTime(tz) | nullable | Processing completion time |

Status machine: `pending → processing → processed | ignored | failed`, with `failed` eventually moving to `abandoned` after 5 retries.

### `container_sessions`

Ephemeral Docker sessions running a skill against a PR.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `installation_id` | UUID | FK(installations.id), NOT NULL, INDEX | Parent installation |
| `user_id` | UUID | FK(github_users.id), nullable, INDEX | User who triggered the session |
| `pr_number` | Integer | NOT NULL | Pull request number |
| `repo_full_name` | String(255) | NOT NULL, INDEX | `"owner/repo"` |
| `skill_name` | String(100) | NOT NULL | Skill executed (e.g. `challenge-me`) |
| `container_id` | String(128) | nullable | Docker container ID (set when running) |
| `status` | Enum `ContainerStatus` (`container_status`, 20 chars) | NOT NULL, INDEX, default `pending` | `pending` / `running` / `completed` / `failed` / `timeout` |
| `started_at` | DateTime(tz) | nullable | Container start time |
| `completed_at` | DateTime(tz) | nullable | Container end time |
| `scorecard` | JSONB | nullable | Parsed `helprs-scorecard` JSON (set on completion for `challenge-me`) |
| `xp_earned` | Integer | nullable | XP extracted from the score card |

### `session_events`

Raw stream-json events persisted from a live session, for replay.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `session_id` | UUID | FK(container_sessions.id, ON DELETE CASCADE), NOT NULL, INDEX | Parent session |
| `event_id` | Integer | NOT NULL, UNIQUE together with `session_id` | Monotonic event index within the session |
| `data` | JSONB | NOT NULL | Raw stream-json event (`assistant`, `system`, `user`, `result`) |

Events are batch-written during SSE streaming via `stream_and_persist()` and read back by `GET /api/v1/containers/sessions/{id}/events`.

## Entity relationships

```
github_users
   │
   │ (user_id, nullable)
   v
installations ──1:1── byok_configs
   │
   │ (installation_id FK)
   ├──── webhook_events  (via github_installation_id — no FK)
   │
   └──── container_sessions ──1:N── session_events
```

## Pydantic schemas

Schemas are grouped by module. Field validators (e.g. `api_key` must start with `sk-ant-`, `labels` de-duplication, `repo_full_name` format) live next to each schema — see the source files for exact rules.

### Identity (`modules/identity/schemas.py`)

- `UserResponse` — `{ id, github_id, github_login, email, avatar_url, created_at }`.
- `TokenResponse` — `{ access_token, token_type }` (default `"bearer"`).
- `DailyCount` — `{ date, count }`.
- `StatusTotals` — `{ completed, failed, timeout, total }`.
- `UserStatsResponse` — `{ daily_counts: DailyCount[], totals: StatusTotals }`.

### Installation (`modules/installation/schemas.py`)

- `BYOKConfigureRequest` — `{ api_key }` (must start with `sk-ant-`, length ≥ 20).
- `BYOKConfigResponse` — `{ key_hint, key_status, validated_at }`.
- `SuppressionLabelsRequest` — `{ labels: string[] }` (≤ 20 items, alphanumeric + `-`, length ≤ 50).
- `SuppressionLabelsResponse` — `{ labels }`.
- `PostResultsSettingRequest` / `PostResultsSettingResponse` — `{ post_results_to_pr: boolean }`.
- `InstallationResponse` — full installation snapshot including BYOK status, `session_count`, `post_results_to_pr`, `suppression_labels`.
- `InstallationDetailResponse` — same shape as `InstallationResponse`.
- `InstallationListResponse` — `{ items: InstallationResponse[], total }`.
- `SessionSummaryResponse` — `{ id, pr_number, repo_full_name, skill_name, status, started_at, completed_at, created_at }`.
- `PaginatedSessionsResponse` — `{ items: SessionSummaryResponse[], total, page, per_page, total_pages }`.

### Container (`modules/container/schemas.py`)

- `CreateSessionRequest` — `{ installation_id: int, pr_number: int ≥ 1, repo_full_name: "owner/repo", skill_name }`.
- `ContainerSessionResponse` — full session snapshot including `scorecard` and `xp_earned`.
- `SendMessageRequest` — `{ content }` (non-empty).
- `SendMessageResponse` — `{ session_id, status, message }`.
- `StopSessionResponse` — `{ id, status, message }`.
- `SessionEventResponse` — `{ event_id, data, created_at }`.
- `SessionEventsListResponse` — `{ session_id, events: SessionEventResponse[], total }`.
- `ScorecardResponse` — `{ session_id, scorecard, xp_earned }`.

## Migrations

Migrations live in `apps/api/alembic/versions/`. Use `alembic history` / `alembic current` to inspect the live state rather than maintaining a hand-written list here. The pre-pivot migration files (`sessions`, `questions`, `answers`, `scores`, `reports`, `feedback`) are still on disk but their corresponding code has been removed since the container pivot — a future squash migration will clean them up.

Create a new migration:

```bash
cd apps/api
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```
