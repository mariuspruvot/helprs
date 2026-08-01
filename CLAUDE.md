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
apps/api/          — FastAPI backend (Python 3.13, uv)
  src/helprs/
    core/          — config, database, dependencies, exceptions, middleware, security
    modules/       — domain modules: identity, installation, webhook, container
    admin/         — SQLAdmin panel + credential management
  tests/           — mirrors modules/ structure
  alembic/         — DB migrations
apps/web/          — React frontend (Vite, TypeScript)
  src/features/    — feature modules: auth, dashboard, installation, session
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

- **App factory**: `helprs.main:create_app()` — module-level `_lifespan` owns the engine and background loops via `AsyncExitStack`: each resource registers its cleanup at acquisition, teardown runs LIFO (cancel loops → drain replay tasks → stop containers → clear factory → dispose engine)
- **Layered modules**: each domain module is `router.py` (thin — validate, call one use case, shape the response) → `service.py` (use cases, no SQL, no HTTP) → `repository.py` (every query, including the soft-delete predicate) → boundary modules for external systems (`github.py`, `anthropic.py`, `docker_client.py`), all returning typed objects rather than dicts. `container` additionally splits `streaming.py` (SSE pipeline) and `cleanup.py` (reaping) out of the service. Every module now has this layering, `webhook` included.
- **Container orchestration**: `container` module manages ephemeral Docker lifecycle, credential injection, result relay. `finalize_session()` (mark completed → scorecard → PR comment) is deliberately detached from the HTTP request, so a client disconnect cannot leave a session stuck RUNNING.
- **Skills as agents**: each skill is a self-contained folder with workflow definitions, mounted into containers
- **SSE passthrough**: backend relays container output to frontend (no AI response generation in backend)
- **Conversation UI**: frontend renders session output as a structured conversation with markdown (react-markdown + remark-gfm), syntax highlighting (shiki with JS regex engine), and diff coloring. Components: `ConversationOutput` (scroll container) -> `MessageBlock` (role dispatch) -> `MarkdownContent` / `CodeBlock`. Data flows as `StreamMessage[]` (structured content blocks) instead of flat text lines.
- **Session persistence**: stream-json events are batch-persisted to `session_events` table (JSONB) during SSE streaming via `stream_and_persist()`. Completed sessions can be replayed from `GET /sessions/{id}/events`. The streaming pipeline is layered: `stream_events()` (raw tuples) -> `stream_and_persist()` (SSE + DB writes) or `stream_output()` (SSE only, for tests).
- **Multi-turn via per-turn invocations**: `--input-format stream-json` exits after each turn (by design). The entrypoint runs `claude -p` for the first turn, then loops reading user messages from a FIFO and calling `claude -c -p` (--continue) for each subsequent turn. Each invocation emits its own `system` init + `result` events — frontend should expect multiple `system`/`result` events per session.
- **Stream-json protocol**: containers emit NDJSON with 5 event types: `system` (init/retry), `assistant` (one event per content block — thinking/text/tool_use), `user` (tool_result), `result` (turn end + metadata), `rate_limit_event`. The `result.result` field duplicates the last assistant text — only display assistant events, use result for status only. No `--include-partial-messages` flag, so no `stream_event` deltas. A 6th type `error` (`{"type":"error","error":{"message":"..."}}`) is emitted by the entrypoint when setup fails (clone/checkout errors). The SSE `done` event includes both `message` and `status` fields — frontend uses `status` to distinguish `completed` vs `failed`.
- **Access control**: Two-tier authorization in `installation/service.py`. `verify_installation_access` checks member-level access (user owns the install, or is an org member via GitHub `/user/orgs`). `verify_session_access` grants instant access to session owners (no API call), falls back to installation membership for other users. `verify_admin_permission` is separate (admin role required for BYOK/settings). All container routes require `get_current_user` + authorization.
- **API prefix**: all routes under `/api/v1`
- **Admin panel**: SQLAdmin at `/admin`, configured in `admin/views.py`
- **Dashboard**: user-facing installation management at `/installations` -- installation list, session history, session replay. Authenticated users redirect from `/` to `/installations`. SQLAdmin remains at `/admin` as superadmin escape hatch.
- **Cross-module queries**: a module never writes SQL over another module's tables. `container/repository.py` owns every `ContainerSession` query, including the aggregates the identity dashboard and the installation router consume.
- **Auth on all REST routes**: identity and installation routers use `Depends(get_current_user)`, container router uses it too. The webhook handler bypasses REST routes entirely — it calls `create_session()` directly (DB record only, no container start). Container start happens when the authenticated frontend calls the REST endpoint.
- **No module `__init__` imports**: the four `modules/*/__init__.py` are docstring-only. Re-exporting a router there pulled the whole router graph back through `core.dependencies` (which imports `identity.models`), so `import helprs.core.dependencies` failed on its own and startup depended on `main.py`'s import order. `tests/test_import_graph.py` guards this.
- **JWT**: PyJWT, not python-jose (unmaintained since 2021, and the source of an unfixable `ecdsa` advisory). `PyJWTError` is the failure type.
- **Fernet keyset, not a single key**: the crypto helpers take `settings.fernet_keys` (`list[str]`, primary first, then `FERNET_KEY_FALLBACKS`) and go through `MultiFernet` — encrypts with the first, decrypts with any. That is what makes key rotation possible without downtime; `helprs.scripts.rotate_credentials` re-encrypts stored rows so a retired key can actually be dropped. Typed `list[str]` rather than `Sequence[str]` on purpose: `str` satisfies `Sequence[str]`, so a caller passing a bare key would type-check.
- **Secrets are `SecretStr`**: read them with `.get_secret_value()`. `SecretStr` defines `__len__`, so truthiness checks work unchanged. `repr(Settings())` used to print every credential, and Sentry uploads locals on any unhandled 500.
- **SSE takes no DB dependency**: FastAPI tears yield-dependencies down only after the streaming body ends, so `Depends(get_db)` — including one behind an auth dependency — pins a pooled connection for the whole stream. The SSE route calls `authenticate_token`/`stream_token` inside a short `get_db_context()` instead.
- **Production env validation**: `Settings` has a `model_validator` that enforces non-empty secrets when `ENVIRONMENT=production`. Tests use `ENVIRONMENT=test` to skip this.
- **Graceful lifecycle**: lifespan reconciles stale RUNNING/PENDING sessions on boot (marks FAILED), and stops all running containers on shutdown. Periodic cleanup uses configurable `CONTAINER_TTL_SECONDS` from settings.

## Skills

Skills are pluggable Claude Code agent definitions in `skills/`. See `skills/SKILL_SPEC.md` for the full specification.

| Skill | Purpose | PR fetch strategy |
|-------|---------|-------------------|
| `challenge-me` | Socratic comprehension quiz on PR changes | `shallow_clone` |
| `eli5` | Explain Like I'm 5 — vulgarize your own code | `shallow_clone` |
| `hot-seat` | Architecture Hot Seat — defend design choices under pressure | `shallow_clone` |
| `pair-debug` | Find the subtle bug Claude injected into your code | `shallow_clone` |
| `test-me` | Predict whether test cases pass or fail on your code | `shallow_clone` |

## Code Style

- Python: ruff with `line-length = 120`, target Python 3.13
- Lint rules: E, F, I, N, UP, B, A, SIM, TCH
- mypy: non-strict with pydantic plugin, **no per-module overrides** — the five that existed were hiding four real errors, all since fixed
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
- **Lost stats tests**: `tests/modules/identity/test_stats.py` (176 lines covering the user stats endpoint) was dropped in the #42 squash; it survives on local branch `feat/dashboard-activity-chart-impl` (62bf88e) — cherry-pick and adapt to boost coverage.
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
- **Multi-worker background tasks**: with `--workers N`, each uvicorn worker runs its own lifespan (webhook reaper + container cleanup). Both are idempotent: reaper uses atomic row-level claim (`mark_processing`), cleanup suppresses double-stop exceptions.
- **Run migrations after checkout**: `docker exec helprs-api-1 uv run alembic current` vs `alembic heads` — if they differ, run `make migrate`. Missing columns cause 500s that surface as browser CORS errors (response lacks CORS headers on unhandled exceptions).
- **API rebuild invalidates tokens**: re-authenticate after an API restart if the deploy changed `SECRET_KEY`. Nothing in the code generates one — `Settings.SECRET_KEY` is required and the app refuses to boot without it.
- **Coolify `--project-directory`**: Coolify sets `--project-directory` to the repo root, not the compose file location. Relative paths in the compose (`context`, `volumes`) must be relative to the repo root (`./apps/api`, not `../../apps/api`).
- **Coolify domain persistence**: Domains set in the Coolify UI may be cleared on redeploy/reload. Verify after each deploy. If persistent issues, add Traefik labels directly in the compose.
- **`.dockerignore` vs `pyproject.toml`**: `apps/api/.dockerignore` excludes `*.md` but `pyproject.toml` references `readme = "README.md"` — `!README.md` exception is required in `.dockerignore` or `uv sync` fails.
- **OAuth callback dual flow**: `GET /api/v1/auth/github/callback` accepts both OAuth login (with `state` CSRF param) and GitHub App installation redirect (with `installation_id`, no `state`). The `state` parameter is optional.
- **GitHub App PEM key**: must be stored as raw PEM (multi-line) in Coolify env vars, NOT base64-encoded. The code passes it directly to `jwt.encode()`.
- **OAuth tokens must be single-line**: Claude OAuth tokens pasted with line breaks cause `Invalid bearer token` errors. Frontend should strip whitespace/newlines from token input.

## Key Decisions

- **Pre-pivot code**: archived on a local-only branch (not on the public remote)
- **No pydantic-ai**: AI orchestration handled by Claude Code CLI in containers, not Python agent code
- **BYOK via dashboard**: Claude OAuth tokens (from `claude setup-token`) stored per installation, encrypted with Fernet, injected as `CLAUDE_CODE_OAUTH_TOKEN` env var into containers. Zero API cost (uses user's Claude subscription).
- **Dashboard over SQLAdmin**: user-facing operations (installation list, session history, token config) go through the dashboard UI; SQLAdmin is the superadmin escape hatch
- **Open source target**: designed for self-hosting with own Claude licenses
- **Post-results to PR**: after session completion, the API can post score card as a PR comment — opt-in per installation via `post_results_to_pr` boolean; extraction and formatting in `container/pr_comment.py`, triggered in `_event_stream()` after `mark_completed()`
- **Coolify deployment**: Two-domain setup via Traefik: `helprs.tech` (web) and `api.helprs.tech` (API). TLS via Let's Encrypt, managed by Coolify. Domains are set in Coolify UI (General > Domains for api / Domains for web) — they may get cleared on redeploy, re-check after each deploy. "Preserve Repository During Deployment" must be enabled so skills are available on the host. The prod compose uses `./` paths (repo-root-relative) because Coolify sets `--project-directory` to the repo root.
- **claude-runner image**: declared in both `docker-compose.yml` and `infra/coolify/docker-compose.prod.yml` as a **build-only service** — `entrypoint: ["/bin/true"]` + `restart: "no"` so the container exits immediately on `up`, leaving only the built image `claude-runner:latest` on the host. The API spawns containers from this image dynamically via the mounted Docker socket. Image tag is hard-coded in `container/service.py:CLAUDE_RUNNER_IMAGE` — it must stay `claude-runner:latest` (no namespace prefix). Earlier attempt with `profiles: [build-only]` was reverted: `profiles:` excludes a service from both build AND run unless the profile is explicitly activated, which Coolify does not do, causing `404 No such image` failures on session spawn.
- **Non-root API container**: production Dockerfile uses `appuser` with `chown -R appuser:appuser /app` for uv cache writes. Docker socket access requires `group_add: ["${DOCKER_GID:-994}"]` in the compose to match the host's docker group GID.
- **BYOK supports OAuth tokens**: `validate_claude_key()` accepts both API keys (`sk-ant-api03-...`) and OAuth tokens (`sk-ant-oat...`). OAuth tokens skip server-side validation (validated at runtime by Claude Code CLI). Frontend setup page guides users to `claude setup-token`.
- **VITE_* build args**: `VITE_API_URL` and `VITE_GITHUB_APP_SLUG` are build-time variables — must be passed as `args` in the compose and declared as `ARG`/`ENV` in `Dockerfile.web`. They cannot be set at runtime.
- **Human-facing docs**: `README.md`, `CONTRIBUTING.md`, `docs/self-hosting.md`, `docs/architecture.md`, `docs/creating-skills.md` -- keep in sync with CLAUDE.md when architecture changes. CLAUDE.md is for AI agents; those docs are for human self-hosters and contributors.
- **No doc archive**: internal/debug notes are not tracked in the public repo (`docs/.archive/` was removed). Keep only the human-facing docs listed above; scratch notes stay local or in PRs.
