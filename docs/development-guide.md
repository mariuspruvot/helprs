# Development Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker + Docker Compose | Latest | Container orchestration |
| Python | 3.12+ | Backend runtime |
| uv | Latest | Python package manager |
| Node.js | 22+ | Frontend runtime |
| npm | 10+ | Frontend package manager |
| PostgreSQL | 16 | Database (or use Docker) |

## Quick Start

```bash
git clone <repo-url> && cd helprs
cp .env.example .env  # Fill in GITHUB_APP_* and secrets
docker compose up --build
# API at http://localhost:8000, Web at http://localhost:5173
```

The first run creates the `helprs` database. Tests need a separate `helprs_test` DB (see [Testing](#testing) below).

## Environment Variables

All variables are documented in `.env.example` with generation instructions. The critical ones for local dev:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres connection string (default works with docker compose) |
| `SECRET_KEY` | JWT signing secret (generate with `secrets.token_urlsafe(48)`) |
| `FERNET_KEY` | Encryption key for stored credentials (`Fernet.generate_key()`) |
| `GITHUB_APP_ID`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_APP_PRIVATE_KEY` | GitHub App credentials |
| `VITE_API_URL` | API base URL seen by the frontend (build-time) |
| `VITE_GITHUB_APP_SLUG` | GitHub App slug used to build the "Install app" link (build-time) |
| `APP_BASE_URL` | Public URL of the frontend (used by backend for PR comments) |
| `CORS_ORIGINS` | JSON array of allowed CORS origins |

Production-only additions: `ENVIRONMENT=production`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `DOCKER_GID`, `SKILLS_HOST_PATH`, `CONTAINER_TTL_SECONDS`, `UVICORN_WORKERS`. See [self-hosting.md](self-hosting.md) and [deploy-coolify.md](deploy-coolify.md).

## Local Development (without Docker)

### Backend

```bash
cd apps/api
uv sync                                  # Install dependencies
uv run alembic upgrade head              # Run migrations
uv run uvicorn helprs.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd apps/web
npm ci                                    # Install dependencies
npx vite --host 0.0.0.0 --port 5173      # Start dev server
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make dev` | `docker compose up --build` |
| `make lint` | ruff check/format + mypy (non-strict) + eslint |
| `make typecheck` | mypy only (API) |
| `make test` | pytest + vitest |
| `make build` | Build production images via `infra/coolify/docker-compose.prod.yml` |
| `make migrate` | `alembic upgrade head` inside the API container |

## Testing

### Backend (pytest)

```bash
cd apps/api
uv run pytest                            # All tests
uv run pytest tests/modules/webhook/     # Single module
uv run pytest -k "test_name"             # By name pattern
```

- Uses `AsyncClient` + `ASGITransport` (no real server needed).
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorators needed.
- `conftest.py` sets env vars **before** any app imports — order matters.
- The test DB (`helprs_test`) must exist: `docker exec helprs-db-1 psql -U helprs -c "CREATE DATABASE helprs_test;"`.

### Frontend (vitest)

```bash
cd apps/web
npx vitest run                           # All tests (single run)
npx vitest                               # Watch mode
npx vitest run src/features/session/     # Single module
```

- Uses `jsdom`, `@testing-library/react`.
- Session-rendering tests must mock `./shiki` to avoid loading real TextMate grammars.

## Code Style

### Python (ruff + mypy)

- `line-length = 120`, target Python 3.12.
- Rules: `E, F, I, N, UP, B, A, SIM, TCH`.
- mypy is **non-strict** with the pydantic plugin; per-module overrides in `apps/api/pyproject.toml`.
- Format / check:
  ```bash
  uv run ruff format src/ tests/
  uv run ruff check src/ tests/
  ```

### TypeScript (eslint)

- Strict mode, `noUnusedLocals`, `noUnusedParameters`.
- `npx eslint src/`.

## Database Migrations

```bash
cd apps/api
uv run alembic revision --autogenerate -m "description"  # Create
uv run alembic upgrade head                               # Apply
uv run alembic downgrade -1                               # Rollback one
```

## Architecture Patterns

See [architecture.md](architecture.md) for the full picture. Quick reference:

**Backend**

- App factory: `helprs.main:create_app()` — lifespan manages the DB engine.
- Flat modules under `apps/api/src/helprs/modules/`: `router.py`, `service.py`, `models.py`, `schemas.py`.
- Modules: `identity`, `installation`, `webhook`, `container`.
- API prefix `/api/v1`. Admin panel at `/admin` (SQLAdmin).

**Frontend**

- Feature-based: `features/{auth, dashboard, installation, session, demo}`.
- Shared under `shared/{api, components}`.
- State: Zustand (auth store) + React Query (server state).
- Routing: `react-router` v7 with `ProtectedRoute` → `AppShell` wrapper.
- See [component-inventory-web.md](component-inventory-web.md).

## Skill Development

Skills are self-contained agent definitions under `skills/`, mounted read-only into the runner container. The repo ships with five built-in skills: `challenge-me`, `eli5`, `hot-seat`, `pair-debug`, `test-me`.

To write a new skill, follow [`skills/SKILL_SPEC.md`](../skills/SKILL_SPEC.md) and the walkthrough in [creating-skills.md](creating-skills.md).

## Gotchas

- **Test conftest order**: env vars must be set before any `from helprs.*` import.
- **GitHub App private key**: multi-line PEM; store as raw PEM in Coolify env vars (not base64). Locally, use `docker-compose.override.yml` with a YAML block scalar if `.env` truncation is an issue.
- **Stale Service Workers**: if SSE fails on `localhost:5173` with `NS_ERROR_INTERCEPTION_FAILED`, unregister the worker in DevTools.
- **Docker socket**: local container-module work requires the API process to see `/var/run/docker.sock`.
- **Always run `make lint` before pushing** — ruff + mypy + eslint must pass.
