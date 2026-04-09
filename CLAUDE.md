## Quick Start

```bash
docker compose up --build        # Start all services (API :8000, Web :5173, Postgres :5432)
make lint                        # Ruff check + format (API), ESLint (Web)
make test                        # pytest (API), vitest (Web)
make migrate                     # Alembic upgrade head
```

## Architecture

Monorepo with two apps and shared infra:

```
apps/api/          — FastAPI backend (Python 3.12, uv)
  src/helprs/
    core/          — config, database, dependencies, middleware, security
    modules/       — domain modules: identity, installation, webhook, billing, comprehension
    admin/         — SQLAdmin panel
  tests/           — mirrors modules/ structure
  alembic/         — DB migrations
apps/web/          — React frontend (Vite, TypeScript)
  src/features/    — feature modules
  src/shared/      — shared components/utils
infra/
  docker/          — Dockerfiles (api, web)
  coolify/         — production docker-compose
```

## Key Patterns

- **App factory**: `helprs.main:create_app()` — lifespan manages DB engine
- **Module structure**: each module has `router.py`, `service.py`, `models.py`, `schemas.py`
- **API prefix**: all routes under `/api/v1`
- **Admin panel**: SQLAdmin at `/admin`, configured in `admin/views.py`

## Code Style

- Python: ruff with `line-length = 120`, target Python 3.12
- Lint rules: E, F, I, N, UP, B, A, SIM, TCH
- `asyncio_mode = "auto"` in pytest — no need for `@pytest.mark.asyncio`

## Testing

```bash
cd apps/api && uv run pytest                    # All API tests
cd apps/api && uv run pytest tests/modules/identity/  # Single module
cd apps/web && npx vitest run                   # All frontend tests
```

- Tests use `AsyncClient` with `ASGITransport` (no real server)
- `conftest.py` sets env vars (DATABASE_URL, SECRET_KEY, etc.) **before** any app imports — order matters

## Environment

Required `.env` at repo root (see docker-compose.yml):
- `DATABASE_URL` — Postgres connection string
- `SECRET_KEY` — app secret
- `GITHUB_APP_ID`, `GITHUB_WEBHOOK_SECRET` — GitHub App config
- `FERNET_KEY` — encryption key for BYOK secrets

## Gotchas

- Always run `make lint` before pushing — ruff + eslint must pass
- DB migrations: `make migrate` inside Docker, or `cd apps/api && uv run alembic upgrade head` locally
- Test conftest **must** set env vars before importing from `helprs.*`
