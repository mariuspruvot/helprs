## Quick Start

```bash
docker compose up --build        # Start all services (API :8000, Web :5173, Postgres :5432)
make lint                        # Ruff check + format + mypy (API), ESLint (Web)
make test                        # pytest (API), vitest (Web)
make migrate                     # Alembic upgrade head
make typecheck                   # mypy (API only)
```

## Architecture

Monorepo with two apps, skills, and shared infra. See [ADR-001](docs/adr-001-claude-code-container-pivot.md) for the pivot decision.

```
apps/api/          — FastAPI backend (Python 3.12, uv)
  src/helprs/
    core/          — config, database, dependencies, exceptions, middleware, security
    modules/       — domain modules: identity, installation, webhook, container
    admin/         — SQLAdmin panel + credential management
  tests/           — mirrors modules/ structure
  alembic/         — DB migrations
apps/web/          — React frontend (Vite, TypeScript)
  src/features/    — feature modules: auth, dashboard, landing, installation, session
  src/shared/      — API client (shared/api/client.ts)
skills/            — Claude Code skill definitions (mounted into ephemeral containers)
infra/
  docker/          — Dockerfiles (api, web, claude-runner)
  coolify/         — production docker-compose
```

## How It Works

1. GitHub PR event hits the webhook receiver
2. API posts a PR comment with a session link
3. User clicks the link (or auto-trigger if configured)
4. Backend spins up an ephemeral Docker container with Claude Code CLI
5. Container runs the assigned skill against the PR (using `gh` CLI for fast checkout)
6. Results stream back via SSE passthrough to the frontend
7. User can send follow-up messages via FIFO; each triggers `claude -c -p` (continues the conversation)
8. Container is destroyed after completion or timeout

**Key**: Users provide their Claude credentials once in the admin panel (BYOK). The backend never calls the Claude API directly -- containers use the credentials natively via Claude Code CLI.

## Key Patterns

- **App factory**: `helprs.main:create_app()` — lifespan manages DB engine
- **Flat modules** (identity, installation, webhook, container): `router.py`, `service.py`, `models.py`, `schemas.py`
- **Container orchestration**: `container` module manages ephemeral Docker lifecycle, credential injection, result relay
- **Skills as agents**: each skill is a self-contained folder with workflow definitions, mounted into containers
- **SSE passthrough**: backend relays container output to frontend (no AI response generation in backend)
- **Conversation UI**: frontend renders session output as a structured conversation with markdown (react-markdown + remark-gfm), syntax highlighting (shiki with JS regex engine), diff coloring, and collapsible tool_use/thinking blocks. Components: `ConversationOutput` (scroll container) -> `MessageBlock` (role dispatch) -> `MarkdownContent` / `CodeBlock` / `ToolUseBlock` / `ThinkingBlock`. Data flows as `StreamMessage[]` (structured content blocks) instead of flat text lines.
- **Session persistence**: stream-json events are batch-persisted to `session_events` table (JSONB) during SSE streaming via `stream_and_persist()`. Completed sessions can be replayed from `GET /sessions/{id}/events`. The streaming pipeline is layered: `stream_events()` (raw tuples) -> `stream_and_persist()` (SSE + DB writes) or `stream_output()` (SSE only, for tests).
- **Multi-turn via per-turn invocations**: `--input-format stream-json` exits after each turn (by design). The entrypoint runs `claude -p` for the first turn, then loops reading user messages from a FIFO and calling `claude -c -p` (--continue) for each subsequent turn. Each invocation emits its own `system` init + `result` events — frontend should expect multiple `system`/`result` events per session.
- **Stream-json protocol**: containers emit NDJSON with 5 event types: `system` (init/retry), `assistant` (one event per content block — thinking/text/tool_use), `user` (tool_result), `result` (turn end + metadata), `rate_limit_event`. The `result.result` field duplicates the last assistant text — only display assistant events, use result for status only. No `--include-partial-messages` flag, so no `stream_event` deltas. A 6th type `error` (`{"type":"error","error":{"message":"..."}}`) is emitted by the entrypoint when setup fails (clone/checkout errors). The SSE `done` event includes both `message` and `status` fields — frontend uses `status` to distinguish `completed` vs `failed`.
- **Access control**: Two-tier authorization in `installation/service.py`. `verify_installation_access` checks member-level access (user owns the install, or is an org member via GitHub `/user/orgs`). `verify_session_access` grants instant access to session owners (no API call), falls back to installation membership for other users. `verify_admin_permission` is separate (admin role required for BYOK/settings). All container routes require `get_current_user` + authorization.
- **API prefix**: all routes under `/api/v1`
- **Admin panel**: SQLAdmin at `/admin`, configured in `admin/views.py`
- **Dashboard**: user-facing installation management at `/installations` -- installation list, session history, session replay. Authenticated users redirect from `/` to `/installations`. SQLAdmin remains at `/admin` as superadmin escape hatch.
- **Cross-module queries**: installation module queries `ContainerSession` model directly (inline import in service functions) for session counts and lists. This avoids circular imports while keeping the API surface on the installation router.
- **Auth on all REST routes**: identity and installation routers use `Depends(get_current_user)`, container router uses it too. The webhook handler bypasses REST routes entirely — it calls `create_session()` directly (DB record only, no container start). Container start happens when the authenticated frontend calls the REST endpoint.
- **Production env validation**: `Settings` has a `model_validator` that enforces non-empty secrets when `ENVIRONMENT=production`. Tests use `ENVIRONMENT=test` to skip this.
- **Graceful lifecycle**: lifespan reconciles stale RUNNING/PENDING sessions on boot (marks FAILED), and stops all running containers on shutdown. Periodic cleanup uses configurable `CONTAINER_TTL_SECONDS` from settings.

## Skills

Skills are pluggable Claude Code agent definitions in `skills/`. See `skills/SKILL_SPEC.md` for the full specification.

| Skill | Purpose | PR fetch strategy |
|-------|---------|-------------------|
| `challenge-me` | Socratic quiz on PR changes | Shallow clone |

## Code Style

- Python: ruff with `line-length = 120`, target Python 3.12
- Lint rules: E, F, I, N, UP, B, A, SIM, TCH
- mypy: non-strict with pydantic plugin, per-module overrides for third-party lib typing issues (see `pyproject.toml`)
- `asyncio_mode = "auto"` in pytest — no need for `@pytest.mark.asyncio`

## Testing

```bash
cd apps/api && uv run pytest                              # All API tests
cd apps/api && uv run pytest tests/modules/identity/      # Single module
cd apps/web && npx vitest run                             # All frontend tests
cd apps/api && uv run alembic revision --autogenerate -m "description"  # New migration
```

- Tests use `AsyncClient` with `ASGITransport` (no real server)
- `conftest.py` sets env vars (DATABASE_URL, SECRET_KEY, etc.) **before** any app imports — order matters
- **`FakeDockerClient` log_lines**: must include trailing `\n` for the line-buffering logic in `stream_events()` to split correctly
- **`get_db_context` in tests**: tests that call `stream_and_persist()` need a `db_with_factory` fixture that calls `set_session_factory()` / `clear_session_factory()` — see `test_service.py` for the pattern
- **Test fixture isolation**: each test file with its own `db_session` fixture using `create_all`/`drop_all` must call `set_session_factory()` / `clear_session_factory()` to avoid PG enum type collisions when run alongside other test files — see `test_pr_comment.py`

## Environment

Required `.env` at repo root — see `.env.example` for all variables with generation instructions.
Key additions for production: `ENVIRONMENT=production`, `ADMIN_PASSWORD`, `CORS_ORIGINS`, `CONTAINER_TTL_SECONDS`, `UVICORN_WORKERS`.

## Gotchas

- **CI coverage threshold**: `--cov-fail-under=70` (current coverage ~75%). Raising to 80% requires covering `admin/views.py`, `main.py` lifespan, and more router branches.
- **Entrypoint parallel I/O**: clone, metadata (`gh pr view --json`), and diff (`gh pr diff`) run as background jobs with `wait`. The `-R` flag lets `gh` hit the API without a local `.git` dir. `set -e` does NOT propagate from background jobs — each `wait $pid` needs explicit `|| exit 1`. The claude-runner image includes `jq` for parsing the combined metadata JSON.
- Always run `make lint` before pushing — ruff + eslint must pass
- **Shiki in tests**: any test rendering session components must mock `./shiki` (highlighter, SHIKI_THEME, SUPPORTED_LANGS) to avoid loading real TextMate grammars in jsdom
- **Test DB**: `docker compose` only creates `helprs` DB. Tests need `helprs_test` — create it once: `docker exec helprs-db-1 psql -U helprs -c "CREATE DATABASE helprs_test;"`
- **aiodocker + asyncio.wait_for = stream corruption**: NEVER use `asyncio.wait_for()` on aiodocker's `container.log(follow=True)` iterator. aiodocker uses a multiplexed stream format (8-byte header + payload) with `readexactly()`. Cancelling mid-read desynchronizes the stream, silently dropping all subsequent events. Use `asyncio.wait()` with timeout instead (keeps the read task alive across keepalive intervals). See `stream_events()` docstring.
- **FIFO open mode must be `<>` (read-write)**: `exec 3>"$FIFO"` (write-only) blocks until a reader exists on the FIFO. Since the reader (`while read ... done < "$FIFO"`) starts later in the script, `>` deadlocks the entrypoint. Always use `exec 3<>"$FIFO"` which opens with O_RDWR and never blocks on FIFOs.
- **No `kill 0` in trap handlers**: `kill 0` sends SIGTERM to bash's own process group while inside the trap handler, causing exit code 139 instead of 0. Docker kills all remaining processes when PID 1 exits — just `exit 0` in the cleanup trap.
- **docker compose must run from project root**: `SKILLS_HOST_PATH=${PWD}/skills` in docker-compose.yml resolves to the wrong path if docker compose is invoked from a subdirectory
- **Debug SSE pipeline**: `claude -p "prompt" --output-format stream-json --verbose 2>/dev/null` captures raw stream-json to validate event parsing
- DB migrations: `make migrate` inside Docker, or `cd apps/api && uv run alembic upgrade head` locally
- Test conftest **must** set env vars before importing from `helprs.*`
- **Agent-readiness**: This repo must be fully understandable by a fresh Claude Code instance with no prior context. Keep docs and CLAUDE.md accurate.
- **Worktree merges**: Always `git stash --include-untracked` before merging worktree branches into main — uncommitted local changes cause modify/delete conflicts
- **Worktrees and node_modules**: `npm install` must be run in each worktree separately — `node_modules` aren't shared from the main tree
- **Shallow clone + `gh pr checkout --detach`**: `gh pr checkout` (without `--detach`) fails on `--depth=1` clones because git can't set up tracking branches from shallow refs. Always use `--detach` — containers don't need tracking branches, just files on disk.
- **Installation IDs in URLs**: frontend routes (`/installations/:id`) use `github_installation_id` (integer, e.g. `123093268`), NOT the internal UUID. All API endpoints (installation AND container session creation) expect the GitHub integer ID. The service layer resolves to internal UUID via `get_installation_by_github_id()`.
- **Fast-failing container race**: if a container exits before the SSE stream fully drains, the client may disconnect before `mark_completed()` runs, leaving the session stuck as RUNNING with 0 persisted events. The 5-minute cleanup task marks these as TIMEOUT. Root cause: generator cancellation on client disconnect skips the post-stream `mark_completed` call in `_event_stream()`.
- **Flaky dispatcher tests**: `test_issues_opened_is_ignored_and_logged` and `test_pull_request_closed_is_ignored` fail when run as part of the full suite due to structlog `configure_logging()` state contamination from `create_app()` in earlier tests. They pass in isolation.
- **Multi-worker background tasks**: with `--workers N`, each uvicorn worker runs its own lifespan (webhook reaper + container cleanup). Both are idempotent: reaper uses atomic row-level claim (`mark_processing`), cleanup suppresses double-stop exceptions.
- **Run migrations after checkout**: `docker exec helprs-api-1 uv run alembic current` vs `alembic heads` — if they differ, run `make migrate`. Missing columns cause 500s that surface as browser CORS errors (response lacks CORS headers on unhandled exceptions).
- **API rebuild invalidates tokens**: `docker compose up --build api` may regenerate SECRET_KEY, invalidating all JWTs and refresh cookies. Re-authenticate after API restarts.

## Key Decisions

- **Pre-pivot code**: preserved on branch `pre-pivot/v1`
- **No pydantic-ai**: AI orchestration handled by Claude Code CLI in containers, not Python agent code
- **BYOK via admin**: credentials stored once per user, injected as ephemeral env vars into containers
- **Dashboard over SQLAdmin**: user-facing operations (installation list, session history, token config) go through the dashboard UI; SQLAdmin is the superadmin escape hatch
- **Open source target**: designed for self-hosting with own Claude licenses
- **Post-results to PR**: after session completion, the API can post score card as a PR comment — opt-in per installation via `post_results_to_pr` boolean; extraction and formatting in `container/pr_comment.py`, triggered in `_event_stream()` after `mark_completed()`
- **Coolify deployment**: TLS terminates at the Coolify reverse proxy, not in nginx. Nginx serves the SPA with security headers but no HTTPS config. SSE `X-Accel-Buffering: no` header is set by the API, not nginx.
- **Non-root API container**: production Dockerfile uses `appuser`. Port 8000 > 1024 so no privilege needed. Docker socket mount still grants Docker access regardless of USER.
