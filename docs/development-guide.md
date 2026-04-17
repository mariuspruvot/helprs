# Development Guide

> Auto-generated on 2026-04-17 (post-pivot rewrite)

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
# Clone and start all services
git clone <repo-url> && cd helprs
cp .env.example .env  # Configure required env vars
docker compose up --build
# API at http://localhost:8000, Web at http://localhost:5173
```

## Environment Variables

Required in `.env` at repo root:

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Postgres connection string | `postgresql+asyncpg://helprs:helprs@localhost:5432/helprs` |
| `SECRET_KEY` | JWT signing secret | `your-secret-key` |
| `GITHUB_APP_ID` | GitHub App numeric ID | `123456` |
| `GITHUB_WEBHOOK_SECRET` | Webhook HMAC secret | `webhook-secret` |
| `FERNET_KEY` | Encryption key for stored credentials | `base64-encoded-key` |
| `GITHUB_APP_PRIVATE_KEY` | RSA private key (via `docker-compose.override.yml`) | PEM format |
| `FRONTEND_URL` | Frontend origin for CORS/redirects | `http://localhost:5173` |

Frontend (Vite):

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | API base URL |
| `VITE_GITHUB_APP_SLUG` | `helprs` | GitHub App slug for install links |

## Local Development (without Docker)

### Backend

```bash
cd apps/api
uv sync                              # Install dependencies
uv run alembic upgrade head           # Run migrations
uv run uvicorn helprs.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd apps/web
npm ci                                # Install dependencies
npx vite --host 0.0.0.0 --port 5173  # Start dev server
```

## Makefile Targets

| Target | Command | Description |
|--------|---------|-------------|
| `make dev` | `docker compose up --build` | Start all services |
| `make lint` | ruff check/format + eslint | Run all linters |
| `make test` | pytest + vitest | Run all test suites |
| `make build` | prod docker-compose build | Build production images |
| `make migrate` | `alembic upgrade head` | Run DB migrations |

## Testing

### Backend (pytest)

```bash
cd apps/api
uv run pytest                         # All tests
uv run pytest tests/modules/webhook/  # Single module
uv run pytest -k "test_name"          # By name pattern
```

- Uses `AsyncClient` + `ASGITransport` (no real server needed)
- `asyncio_mode = "auto"` -- no `@pytest.mark.asyncio` needed
- `conftest.py` sets env vars **before** any app imports (order matters)
- CI runs against real Postgres service container

### Frontend (vitest)

```bash
cd apps/web
npx vitest run                        # All tests (single run)
npx vitest                            # Watch mode
npx vitest run src/features/session/  # Single module
```

- Uses `jsdom` environment
- `@testing-library/react` for component tests

## Code Style

### Python (ruff)

- Line length: 120
- Target: Python 3.12
- Rules: `E, F, I, N, UP, B, A, SIM, TCH`
- Auto-format: `uv run ruff format src/ tests/`
- Check: `uv run ruff check src/ tests/`

### TypeScript (eslint)

- Strict mode enabled
- `noUnusedLocals`, `noUnusedParameters`
- Check: `npx eslint src/`

## Database Migrations

```bash
# Create new migration
cd apps/api
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback one step
uv run alembic downgrade -1
```

## Project Architecture Patterns

### Backend

- **App factory**: `helprs.main:create_app()` -- lifespan manages DB engine
- **Flat modules** (identity, installation, webhook): `router.py`, `service.py`, `models.py`, `schemas.py`
- **Container module** (new): orchestrates ephemeral Docker containers for skill execution
- **API prefix**: All routes under `/api/v1`
- **Admin panel**: SQLAdmin at `/admin`

### Frontend

- **Feature-based**: `features/{auth,landing,dashboard,installation,session}`
- **Shared infrastructure**: `shared/{api,components,hooks,theme,types,utils}`
- **State**: Zustand (auth + session stores) + React Query (session data)
- **Routing**: react-router v7 with `ProtectedRoute` -> `AppShell` wrapper
- **Responsive**: SplitLayout (desktop) / TabbedLayout (tablet) / MobileLayout (mobile)

## Skill Development

Skills are self-contained agent definitions in the `skills/` directory. Each skill folder is mounted into the ephemeral claude-runner container as a volume. Claude Code discovers and executes them natively.

```
skills/
+-- challenge-me/     # Socratic quiz on PR changes
+-- code-review/      # Multi-layer adversarial code review
+-- security-audit/   # Vulnerability scan on the diff
+-- doc-generator/    # Generate/update impacted documentation
+-- test-suggester/   # Propose missing test cases
```

Skill structure and development guidelines: *Coming in Phase 2.*

## Gotchas

- **Test conftest order**: `conftest.py` MUST set env vars before importing from `helprs.*`
- **RSA key in override**: `docker-compose.override.yml` contains the GitHub App private key as YAML block scalar (docker-compose can't do multi-line `.env` values)
- **Zombie Service Workers**: If SSE fails with `NS_ERROR_INTERCEPTION_FAILED` on localhost:5173, unregister stale Workbox SW in DevTools
- **Nginx in prod**: Serves only static files, no API proxy -- Coolify/external reverse proxy handles `/api/*` routing
- **Always lint before pushing**: `make lint` must pass (ruff + eslint)
- **Docker socket**: For local container module development, the API process needs access to the Docker socket
