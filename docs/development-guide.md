# Development Guide

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker + Docker Compose | latest | Container orchestration |
| Python | 3.12+ | Backend runtime |
| uv | latest | Python package manager |
| Node.js | 22+ | Frontend runtime |
| npm | latest | Frontend package manager |

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your GitHub App credentials, SECRET_KEY, FERNET_KEY

# 2. Start all services
docker compose up --build
# or
make dev

# API: http://localhost:8000
# Web: http://localhost:5173
# DB:  localhost:5432 (helprs/helprs/helprs)
```

## Environment Setup

### Required Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | How to generate |
|----------|-----------------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `FERNET_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GITHUB_APP_*` | Create a GitHub App at github.com/settings/apps |
| `DATABASE_URL` | `postgresql+asyncpg://helprs:helprs@localhost:5432/helprs` (local) |

### Multi-line RSA Key

Docker Compose `.env` files cannot handle multi-line values. Use `docker-compose.override.yml`:

```yaml
services:
  api:
    environment:
      GITHUB_APP_PRIVATE_KEY: |
        -----BEGIN RSA PRIVATE KEY-----
        ...your key...
        -----END RSA PRIVATE KEY-----
```

## Development Commands

| Command | What it does |
|---------|-------------|
| `make dev` | `docker compose up --build` — start all services |
| `make lint` | ruff check + format (API) + eslint (Web) |
| `make test` | pytest (API) + vitest (Web) |
| `make build` | Build production Docker images |
| `make migrate` | `alembic upgrade head` locally |

## Backend Development

### Running locally (without Docker)

```bash
cd apps/api
uv sync                              # Install all dependencies
uv run alembic upgrade head           # Run migrations
uv run uvicorn helprs.main:app --host 0.0.0.0 --port 8000 --reload
```

### Linting

```bash
cd apps/api
uv run ruff check src/ tests/        # Lint
uv run ruff format --check src/ tests/  # Format check
uv run ruff format src/ tests/        # Auto-format
```

Config: `pyproject.toml` — line-length=120, target Python 3.12, rules: E, F, I, N, UP, B, A, SIM, TCH.

### Testing

```bash
cd apps/api
uv run pytest                         # All tests
uv run pytest tests/modules/identity/ # Single module
uv run pytest -x -v                   # Stop on first failure, verbose
```

- `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio`
- Tests use `AsyncClient` with `ASGITransport` (no real server)
- `conftest.py` sets env vars **before** any app imports (order matters)

### Creating Migrations

```bash
cd apps/api
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

### Admin Panel

Available at `http://localhost:8000/admin`. Auto-login in development mode.

## Frontend Development

### Running locally (without Docker)

```bash
cd apps/web
npm ci                                # Install dependencies
npx vite                              # Dev server on :5173
```

### Linting

```bash
cd apps/web
npx eslint src/                       # ESLint
```

### Testing

```bash
cd apps/web
npx vitest run                        # All tests
npx vitest run --watch                # Watch mode
```

### Build

```bash
cd apps/web
npm run build                         # tsc + vite build -> dist/
```

### Path Aliases

`@/*` maps to `./src/*` (configured in `tsconfig.json`).

## Code Style

### Backend (Python)

- Ruff with `line-length = 120`, target Python 3.12
- Rules: E (pycodestyle), F (pyflakes), I (isort), N (pep8-naming), UP (pyupgrade), B (bugbear), A (builtins), SIM (simplify), TCH (type-checking)
- Async-first: all DB operations use async SQLAlchemy

### Frontend (TypeScript)

- TypeScript 6.0 with strict mode
- ESLint + typescript-eslint
- Tailwind CSS 4 for styling
- ES2023 target, bundler module resolution

## Module Structure

### Backend — Simple Modules

```
module/
  models.py   — SQLAlchemy ORM models
  schemas.py  — Pydantic DTOs
  router.py   — FastAPI routes
  service.py  — Business logic
```

### Backend — Clean Architecture (comprehension)

```
module/
  domain/          — Entities, value objects, protocols
  application/     — Commands, queries, handlers
  infrastructure/  — ORM, repositories, external APIs
  presentation/    — Routes, SSE, schemas, DI
```

### Frontend — Feature Modules

```
feature/
  ComponentA.tsx   — UI component
  ComponentB.tsx   — UI component
  store.ts         — Zustand store (if needed)
  api.ts           — API calls
  types.ts         — TypeScript types
```

## Gotchas

- Always run `make lint` before pushing — CI will fail otherwise
- Test conftest **must** set env vars before importing from `helprs.*`
- `GITHUB_APP_PRIVATE_KEY` multi-line workaround: use `docker-compose.override.yml`
- If SSE/fetch fails with `NS_ERROR_INTERCEPTION_FAILED`, unregister the zombie Workbox Service Worker at localhost:5173
