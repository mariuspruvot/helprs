# Deployment Guide

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Overview

helPRs deploys via **Coolify** triggered by GitHub Actions on push to `main`. Docker images are built and pushed to GitHub Container Registry (GHCR), then Coolify pulls and redeploys.

## Deployment Pipeline

```
Push to main
     │
     ▼
┌─────────────────────────────────────────────┐
│  GitHub Actions: deploy.yml                  │
│                                              │
│  Job 1: build-and-push                       │
│  ├── Login to ghcr.io (GITHUB_TOKEN)        │
│  ├── Build api:latest + api:<sha>            │
│  └── Build web:latest + web:<sha>            │
│                                              │
│  Job 2: deploy (conditional on secrets)      │
│  └── POST to COOLIFY_WEBHOOK_URL             │
│      (Bearer: COOLIFY_TOKEN)                 │
└─────────────────────────────────────────────┘
     │
     ▼
  Coolify pulls images and redeploys
```

## CI Pipeline (Gate)

All pushes and PRs to `main` trigger `ci.yml`:

| Job | What | Must Pass? |
|-----|------|-----------|
| lint-backend | ruff check + format | Yes |
| test-backend | pytest (with Postgres service container) | Yes |
| lint-frontend | eslint | Yes |
| test-frontend | vitest | Yes |
| build | docker build (both targets) | Gated on all 4 above |

## Production Docker Images

### API (`Dockerfile.api` — production stage)

- Base: `python:3.12-slim`
- `uv sync --no-dev` (production deps only)
- CMD: `alembic upgrade head && uvicorn helprs.main:app --host 0.0.0.0 --port 8000`
- Auto-runs migrations on startup

### Web (`Dockerfile.web` — production stage)

- Build stage: `node:22-slim` with `npm run build`
- Production: `nginx:alpine` serving static assets from `/usr/share/nginx/html`
- SPA fallback via `try_files $uri $uri/ /index.html`
- Asset caching: `expires 1y` for `/assets/` and `/fonts/`
- Gzip enabled

## Production Compose (`infra/coolify/docker-compose.prod.yml`)

| Service | Port | Restart Policy | Notes |
|---------|------|---------------|-------|
| api | 8000 | unless-stopped | env_file, depends_on db (healthy) |
| web | 80 | unless-stopped | nginx serving SPA |
| db | internal | unless-stopped | postgres:16-alpine, pgdata volume |

## Required Secrets (GitHub Actions)

| Secret | Purpose |
|--------|---------|
| `GITHUB_TOKEN` | Auto-provided, GHCR login |
| `COOLIFY_WEBHOOK_URL` | Coolify deployment webhook endpoint |
| `COOLIFY_TOKEN` | Bearer auth for Coolify webhook |

## Required Environment Variables (Production)

| Variable | Notes |
|----------|-------|
| `DATABASE_URL` | Use `postgresql+asyncpg://...` format |
| `SECRET_KEY` | Strong random value |
| `FERNET_KEY` | Fernet.generate_key() output |
| `GITHUB_APP_ID` | Numeric GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | RSA private key (manage via Coolify env) |
| `GITHUB_CLIENT_ID` | OAuth client ID |
| `GITHUB_CLIENT_SECRET` | OAuth client secret |
| `GITHUB_WEBHOOK_SECRET` | Webhook HMAC verification |
| `APP_BASE_URL` | Public frontend URL |
| `VITE_API_URL` | Public API URL |
| `SENTRY_DSN` | Optional — error tracking |

## Health Check

- `GET /health` returns `{"status": "ok"}` (no auth required)
- Database health: `pg_isready` (5s interval, 3s timeout, 5 retries)

## Infrastructure Notes

- Database volume (`pgdata`) is persistent across deployments
- API auto-runs `alembic upgrade head` on every start
- No dedicated reverse proxy documented (Coolify likely handles TLS termination)
