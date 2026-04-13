# Data Models — Backend (api)

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

All tables inherit `id` (UUID PK), `created_at` (timestamptz, server_default=now()), `updated_at` (timestamptz, server_default=now(), onupdate=now()) from `Base`.

---

## Entity-Relationship Overview

```
github_users
    |
installations ──── byok_configs (1:1)
    |
sessions ──┬── questions ──── answers (1:1)
           ├── scores (1:1)
           ├── question_reports
           └── session_feedback (1:1)

webhook_events (standalone)
```

---

## Tables

### `github_users`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| github_id | BIGINT | UNIQUE, NOT NULL, indexed |
| github_login | VARCHAR(255) | NOT NULL, indexed |
| email | VARCHAR(255) | nullable |
| avatar_url | VARCHAR(512) | nullable |
| github_access_token_enc | VARCHAR(512) | NOT NULL (Fernet-encrypted) |
| created_at | TIMESTAMPTZ | server_default=now() |
| updated_at | TIMESTAMPTZ | server_default=now() |

### `installations`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| github_installation_id | BIGINT | UNIQUE, NOT NULL, indexed |
| account_login | VARCHAR(255) | NOT NULL |
| account_id | BIGINT | NOT NULL |
| account_type | VARCHAR(50) | NOT NULL (`User` or `Organization`) |
| repository_selection | VARCHAR(20) | NOT NULL (`all` or `selected`) |
| app_slug | VARCHAR(255) | NOT NULL |
| target_type | VARCHAR(50) | NOT NULL |
| permissions | JSONB | nullable |
| events | JSONB | nullable |
| suppression_labels | JSONB | nullable, default=[] |
| suspended_at | TIMESTAMPTZ | nullable |
| deleted_at | TIMESTAMPTZ | nullable (soft-delete) |
| created_at, updated_at | TIMESTAMPTZ | standard |

**Relationships:** `byok_config` -- one-to-one with `byok_configs`

### `byok_configs`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| installation_id | UUID | FK -> installations.id, UNIQUE, indexed, NOT NULL |
| encrypted_api_key | VARCHAR(1024) | NOT NULL (Fernet-encrypted Anthropic API key) |
| key_status | VARCHAR(20) | default="valid" |
| validated_at | TIMESTAMPTZ | nullable |
| key_hint | VARCHAR(20) | nullable (e.g. `...abcd`) |
| created_at, updated_at | TIMESTAMPTZ | standard |

### `webhook_events`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| delivery_id | VARCHAR(64) | UNIQUE, NOT NULL, indexed (GitHub X-GitHub-Delivery) |
| event_type | VARCHAR(50) | NOT NULL, indexed |
| action | VARCHAR(50) | nullable |
| github_installation_id | BIGINT | nullable, indexed |
| payload | JSONB | NOT NULL |
| status | VARCHAR(20) | NOT NULL, indexed, default="pending" |
| retry_count | INTEGER | NOT NULL, default=0 |
| error_message | TEXT | nullable |
| processed_at | TIMESTAMPTZ | nullable |
| created_at, updated_at | TIMESTAMPTZ | standard |

**Status lifecycle:** `pending` -> `processing` -> `processed` | `ignored` | `failed` | `abandoned`

### `sessions`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| installation_id | UUID | FK -> installations.id, NOT NULL, indexed |
| github_installation_id | BIGINT | NOT NULL, indexed |
| repo_full_name | VARCHAR(512) | NOT NULL, indexed |
| repo_owner | VARCHAR(255) | NOT NULL |
| repo_name | VARCHAR(255) | NOT NULL |
| pr_number | INTEGER | NOT NULL |
| pr_title | VARCHAR(1024) | NOT NULL |
| pr_head_sha | VARCHAR(40) | NOT NULL |
| pr_diff_url | VARCHAR(1024) | NOT NULL |
| role | VARCHAR(20) | NOT NULL (`author` or `reviewer`) |
| status | VARCHAR(20) | NOT NULL, default="pending" |
| total_questions | INTEGER | NOT NULL, default=0 |
| created_at, updated_at | TIMESTAMPTZ | standard |

**Unique constraint:** `uq_sessions_installation_pr_role` on (installation_id, repo_full_name, pr_number, role)

**Status lifecycle:** `pending` -> `active` -> `completed`

### `questions`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| session_id | UUID | FK -> sessions.id (CASCADE), NOT NULL |
| number | INTEGER | NOT NULL (1-indexed) |
| topic | VARCHAR(32) | NOT NULL (architecture, edge_cases, tradeoffs, impact, testing, correctness) |
| text_hash | VARCHAR(64) | NOT NULL (SHA-256 hex -- no verbatim text stored) |
| created_at, updated_at | TIMESTAMPTZ | standard |

**Unique constraint:** `uq_questions_session_number` on (session_id, number)

### `answers`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| question_id | UUID | FK -> questions.id (CASCADE), NOT NULL |
| text_hash | VARCHAR(64) | NOT NULL (SHA-256 -- no verbatim text stored) |
| latency_ms | BIGINT | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | standard |

**Unique constraint:** `uq_answers_question_id` on (question_id) -- exactly one answer per question

### `scores`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| session_id | UUID | FK -> sessions.id (CASCADE), NOT NULL |
| depth | INTEGER | NOT NULL, CHECK 0-10 |
| accuracy | INTEGER | NOT NULL, CHECK 0-10 |
| completeness | INTEGER | NOT NULL, CHECK 0-10 |
| insight | INTEGER | NOT NULL, CHECK 0-10 |
| verdict | VARCHAR(20) | NOT NULL (exceptional/strong/adequate/weak/insufficient) |
| gap_summary | JSONB | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | standard |

**Unique constraint:** `uq_scores_session_id` on (session_id)

### `question_reports`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| session_id | UUID | FK -> sessions.id (CASCADE), NOT NULL |
| question_number | INTEGER | NOT NULL |
| reason | VARCHAR(32) | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | standard |

**Unique constraint:** `uq_question_reports_session_question` on (session_id, question_number)

### `session_feedback`

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PK |
| session_id | UUID | FK -> sessions.id (CASCADE), NOT NULL |
| rating | BOOLEAN | NOT NULL (true = thumbs-up) |
| comment | TEXT | nullable, CHECK length <= 2000 |
| created_at, updated_at | TIMESTAMPTZ | standard |

**Unique constraint:** `uq_session_feedback_session_id` on (session_id)

---

## Migration Chain

```
f91a5f49775b  github_users
     |
bcc0b5382ffd  installations
     |
9036c7377667  sessions
     |
98dc1b6e754e  webhook_events
     |
792dfdfd0924  byok_configs + suppression_labels
     |
a1b2c3d4e5f6  questions + total_questions column
     |
b2c3d4e5f6a7  answers
     |
c3d4e5f6a7b8  scores
     |
d4e5f6a7b8c9  question_reports + session_feedback
```
