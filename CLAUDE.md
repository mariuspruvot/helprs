## Quick Start

```bash
docker compose up --build        # Start all services (API :8000, Web :5173, Postgres :5432)
make lint                        # Ruff check + format (API), ESLint (Web)
make test                        # pytest (API), vitest (Web)
make migrate                     # Alembic upgrade head
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
  src/features/    — feature modules: auth, landing, installation, session
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

## Skills

Skills are pluggable Claude Code agent definitions in `skills/`. See `skills/SKILL_SPEC.md` for the full specification.

| Skill | Purpose | PR fetch strategy |
|-------|---------|-------------------|
| `challenge-me` | Socratic quiz on PR changes | Shallow clone |

## Code Style

- Python: ruff with `line-length = 120`, target Python 3.12
- Lint rules: E, F, I, N, UP, B, A, SIM, TCH
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

## Environment

Required `.env` at repo root (see docker-compose.yml):
- `DATABASE_URL` — Postgres connection string
- `SECRET_KEY` — app secret
- `GITHUB_APP_ID`, `GITHUB_WEBHOOK_SECRET` — GitHub App config
- `FERNET_KEY` — encryption key for stored credentials

## Gotchas

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

## Key Decisions

- **Pre-pivot code**: preserved on branch `pre-pivot/v1`
- **No pydantic-ai**: AI orchestration handled by Claude Code CLI in containers, not Python agent code
- **BYOK via admin**: credentials stored once per user, injected as ephemeral env vars into containers
- **Open source target**: designed for self-hosting with own Claude licenses
