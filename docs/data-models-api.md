# Data Models -- Backend

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Database Schema

All tables inherit from `Base` which provides:

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | UUID | PK | `uuid4()` | Primary key |
| created_at | DateTime(tz) | NOT NULL | `now()` | Row creation time |
| updated_at | DateTime(tz) | NOT NULL | `now()` (onupdate: `now()`) | Last modification time |

---

### github_users

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | UUID | PK | uuid4() | inherited |
| github_id | BigInteger | UNIQUE, NOT NULL, INDEX | -- | GitHub numeric user ID |
| github_login | String(255) | NOT NULL, INDEX | -- | GitHub username |
| email | String(255) | nullable | -- | Email address |
| avatar_url | String(512) | nullable | -- | GitHub avatar URL |
| github_access_token_enc | String(512) | NOT NULL | -- | Fernet-encrypted GitHub OAuth token |
| created_at | DateTime(tz) | NOT NULL | now() | inherited |
| updated_at | DateTime(tz) | NOT NULL | now() | inherited |

---

### installations

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | UUID | PK | uuid4() | inherited |
| github_installation_id | BigInteger | UNIQUE, NOT NULL, INDEX | -- | GitHub App installation ID |
| account_login | String(255) | NOT NULL | -- | Account name (user/org) |
| account_id | BigInteger | NOT NULL | -- | GitHub account numeric ID |
| account_type | String(50) | NOT NULL | -- | `"User"` or `"Organization"` |
| repository_selection | String(20) | NOT NULL | -- | `"all"` or `"selected"` |
| app_slug | String(255) | NOT NULL | -- | GitHub App slug |
| target_type | String(50) | NOT NULL | -- | `"Organization"` or `"User"` |
| permissions | JSON | nullable | -- | GitHub App permissions granted |
| events | JSON | nullable | -- | Subscribed webhook events |
| suppression_labels | JSON | nullable | `[]` | PR labels that suppress session creation |
| suspended_at | DateTime(tz) | nullable | -- | When installation was suspended |
| deleted_at | DateTime(tz) | nullable | -- | Soft-delete timestamp |
| created_at | DateTime(tz) | NOT NULL | now() | inherited |
| updated_at | DateTime(tz) | NOT NULL | now() | inherited |

**Relationships:** `byok_config` -- one-to-one with `BYOKConfig`

---

### byok_configs

Stores encrypted Claude credentials per installation. Post-pivot, this stores Claude Code credentials (not just API keys).

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | UUID | PK | uuid4() | inherited |
| installation_id | UUID | FK(installations.id), UNIQUE, NOT NULL, INDEX | -- | Parent installation |
| encrypted_api_key | String(1024) | NOT NULL | -- | Fernet-encrypted credentials |
| key_status | String(20) | NOT NULL | `"valid"` | Validation status |
| validated_at | DateTime(tz) | nullable | -- | Last validation timestamp |
| key_hint | String(20) | nullable | -- | Last 4 chars hint (`"...xxxx"`) |
| created_at | DateTime(tz) | NOT NULL | now() | inherited |
| updated_at | DateTime(tz) | NOT NULL | now() | inherited |

---

### webhook_events

| Column | Type | Constraints | Default | Description |
|--------|------|-------------|---------|-------------|
| id | UUID | PK | uuid4() | inherited |
| delivery_id | String(64) | UNIQUE, NOT NULL, INDEX | -- | `X-GitHub-Delivery` header |
| event_type | String(50) | NOT NULL, INDEX | -- | `X-GitHub-Event` header value |
| action | String(50) | nullable | -- | Payload `action` field |
| github_installation_id | BigInteger | nullable, INDEX | -- | Extracted installation ID |
| payload | JSONB | NOT NULL | -- | Raw webhook JSON payload |
| status | String(20) | NOT NULL, INDEX | `"pending"` | `pending` / `processing` / `processed` / `failed` / `ignored` / `abandoned` |
| retry_count | Integer | NOT NULL | `0` | Number of processing attempts |
| error_message | Text | nullable | -- | Last error message |
| processed_at | DateTime(tz) | nullable | -- | When processing completed |
| created_at | DateTime(tz) | NOT NULL | now() | inherited |
| updated_at | DateTime(tz) | NOT NULL | now() | inherited |

**Status machine:** `pending` -> `processing` -> `processed` | `ignored` | `failed` -> (after 5 retries) `abandoned`

---

### Container Session Models -- Coming in Phase 2

The container module will introduce new models for tracking container sessions. Expected tables:

| Table | Purpose |
|-------|---------|
| `container_sessions` | Tracks ephemeral container lifecycle (skill, status, start/end time, installation link) |

Exact schema will be defined during container module implementation. The existing `sessions`, `questions`, `answers`, `scores`, `question_reports`, and `session_feedback` tables from the comprehension module will be removed.

---

## Entity Relationship Diagram

```
installations --1:1-- byok_configs
      |
      | 1:N
      v
webhook_events

github_users (standalone)

container_sessions (Coming in Phase 2)
```

---

## Pydantic Schemas

### Identity Module

#### UserResponse

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | User ID |
| github_id | int | GitHub numeric ID |
| github_login | str | GitHub username |
| email | str \| None | Email |
| avatar_url | str \| None | Avatar URL |
| created_at | datetime | Created timestamp |

#### TokenResponse

| Field | Type | Description |
|-------|------|-------------|
| access_token | str | JWT access token |
| token_type | str | `"bearer"` |

### Installation Module

#### BYOKConfigureRequest

| Field | Type | Validation | Description |
|-------|------|------------|-------------|
| api_key | str | Min 20 chars | Claude credentials |

#### BYOKConfigResponse

| Field | Type | Description |
|-------|------|-------------|
| key_hint | str | Last 4 chars |
| key_status | str | Status |
| validated_at | datetime \| None | Validation time |

#### InstallationResponse

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Internal ID |
| github_installation_id | int | GitHub installation ID |
| account_login | str | Account name |
| account_type | str | User or Organization |
| repository_selection | str | all or selected |
| suspended_at | datetime \| None | Suspension time |
| created_at | datetime | Creation time |
| byok_configured | bool | BYOK status |
| byok_key_hint | str \| None | Key hint |
| byok_key_status | str \| None | Key status |
| byok_validated_at | datetime \| None | Validation time |
| suppression_labels | list[str] | Labels |

---

## Migration History (Pre-Pivot)

| Revision | Date | Description |
|----------|------|-------------|
| `f91a5f49775b` | 2026-04-09 | Add `github_users` table |
| `bcc0b5382ffd` | 2026-04-09 | Add `installations` table |
| `792dfdfd0924` | 2026-04-09 | Add `byok_configs` table + `suppression_labels` column |
| `98dc1b6e754e` | 2026-04-10 | Add `webhook_events` table |
| `9036c7377667` | 2026-04-10 | Add `sessions` table |
| `a1b2c3d4e5f6` | 2026-04-10 | Add `questions` table |
| `b2c3d4e5f6a7` | 2026-04-11 | Add `answers` table |
| `c3d4e5f6a7b8` | 2026-04-12 | Add `scores` table |
| `d4e5f6a7b8c9` | 2026-04-12 | Add `question_reports` and `session_feedback` tables |

Post-pivot migrations will remove comprehension-related tables (`sessions`, `questions`, `answers`, `scores`, `question_reports`, `session_feedback`) and add `container_sessions`.
