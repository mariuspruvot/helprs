# Architecture — Infrastructure (infra)

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Executive Summary

Docker-based infrastructure for **helPRs** with multi-stage builds, local development via docker-compose, production deployment via Coolify, and CI/CD through GitHub Actions.

## Docker Architecture

### API Image (`infra/docker/Dockerfile.api`)

| Stage | Base Image | Key Steps |
|-------|-----------|-----------|
| `dev` | python:3.12-slim | `uv sync` (all deps), copies src + alembic. No CMD (compose provides). Source volume-mounted at runtime. |
| `production` | python:3.12-slim | `uv sync --no-dev`, CMD: `alembic upgrade head && uvicorn helprs.main:app` on port 8000 |

Both stages copy `uv` binary from `ghcr.io/astral-sh/uv:latest`.

### Web Image (`infra/docker/Dockerfile.web`)

| Stage | Base Image | Key Steps |
|-------|-----------|-----------|
| `dev` | node:22-slim | `npm ci`, CMD: `npx vite --host 0.0.0.0` |
| `build` | node:22-slim | `npm ci` + `npm run build` -> `/app/dist` |
| `production` | nginx:alpine | Copies dist from build stage, applies nginx.conf |

### Nginx Configuration

- Listens on port 80, catch-all server name
- SPA fallback: `try_files $uri $uri/ /index.html`
- Static asset caching: `/assets/` and `/fonts/` get `expires 1y` with `Cache-Control: public, immutable`
- Gzip enabled for text, CSS, JSON, JS, XML, SVG (256-byte minimum)

## Local Development

**`docker-compose.yml`** — 3 services:

| Service | Target | Ports | Volumes | Hot Reload |
|---------|--------|-------|---------|------------|
| `api` | dev | 8000 | `apps/api/src`, `apps/api/alembic` | uvicorn `--reload` |
| `web` | dev | 5173 | `apps/web/src` | Vite HMR + `CHOKIDAR_USEPOLLING=true` |
| `db` | postgres:16-alpine | 5432 | `pgdata` named volume | N/A |

- API depends on `db` with health check (`pg_isready`, 5s interval)
- API command: `alembic upgrade head && uvicorn ... --reload`
- DB credentials: `helprs/helprs/helprs`
- `docker-compose.override.yml`: Injects `GITHUB_APP_PRIVATE_KEY` as YAML block scalar (multi-line RSA key workaround)

## Production Deployment

**`infra/coolify/docker-compose.prod.yml`** — same 3 services with production targets:

| Service | Target | Ports | Notes |
|---------|--------|-------|-------|
| `api` | production | 8000 | `env_file: ../../.env`, `restart: unless-stopped` |
| `web` | production | 80 | nginx serving built SPA, `restart: unless-stopped` |
| `db` | postgres:16-alpine | (not exposed) | `restart: unless-stopped`, same health check |

**Deployment flow**: Coolify webhook triggered by GitHub Actions deploy workflow.

## CI/CD Pipeline

### `ci.yml` — Continuous Integration

**Trigger**: All pushes + PRs to `main`

| Job | Runner | Steps |
|-----|--------|-------|
| `lint-backend` | ubuntu | `uv sync --frozen` -> `ruff check` + `ruff format --check` |
| `test-backend` | ubuntu + postgres:16-alpine service | `uv run pytest` with test env vars |
| `lint-frontend` | ubuntu + Node 22 | `npm ci` -> `npx eslint src/` |
| `test-frontend` | ubuntu + Node 22 | `npm ci` -> `npx vitest run` |
| `build` | ubuntu | **Gated on all 4 above**. `docker build` for both production targets (no push) |

### `deploy.yml` — Deploy to Production

**Trigger**: Push to `main` only

| Job | Steps |
|-----|-------|
| `build-and-push` | Login to `ghcr.io`, build + push `api:latest/:sha` and `web:latest/:sha` |
| `deploy` | POST to `COOLIFY_WEBHOOK_URL` with bearer auth (conditional on secret existing) |

## Environment Configuration

| Variable | Purpose | Required |
|----------|---------|----------|
| `DATABASE_URL` | Postgres async connection (asyncpg) | Yes |
| `SECRET_KEY` | JWT signing + SQLAdmin sessions | Yes |
| `FERNET_KEY` | Fernet encryption for stored tokens/keys | Yes |
| `GITHUB_APP_ID` | GitHub App numeric ID | Yes |
| `GITHUB_APP_PRIVATE_KEY` | RSA private key (multi-line) | Yes |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID | Yes |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth client secret | Yes |
| `GITHUB_WEBHOOK_SECRET` | Webhook HMAC verification | Yes |
| `ANTHROPIC_API_KEY` | Demo mode only (BYOK-only model) | Optional |
| `SENTRY_DSN` | Error tracking | Optional |
| `VITE_API_URL` | Frontend API base URL | Yes |
| `APP_BASE_URL` | Backend user-facing links (PR comments) | Yes |

## Makefile Commands

| Target | Command | Description |
|--------|---------|-------------|
| `dev` | `docker compose up --build` | Start all services with rebuild |
| `lint` | ruff check + format (API) + eslint (Web) | Run all linters |
| `test` | pytest (API) + vitest (Web) | Run all test suites |
| `build` | docker compose -f prod build | Build production images |
| `migrate` | `alembic upgrade head` | Run DB migrations locally |
| `types` | (placeholder) | OpenAPI -> TypeScript (not yet implemented) |
