# Deployment Guide

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Architecture Overview

```
+--------------+     +--------------+     +--------------+
|   Coolify    |---->|   Nginx      |     |   API        |
|  (Reverse    |     |   (Web)      |     |  (FastAPI)   |
|   Proxy)     |---->|   :80        |     |   :8000      |
+--------------+     +--------------+     +--------------+
                                               |       |
                                         +-----v------+ |
                                         | PostgreSQL | |
                                         |   :5432    | |
                                         +------------+ |
                                                        |
                                         +--------------v-+
                                         | claude-runner   |
                                         | (ephemeral,     |
                                         |  spawned on     |
                                         |  demand)        |
                                         +-----------------+
```

- **Web container**: Nginx serving static React build, SPA routing via `try_files`
- **API container**: Uvicorn running FastAPI, auto-runs `alembic upgrade head` on startup. Spawns ephemeral claude-runner containers via Docker SDK.
- **Database**: PostgreSQL 16 with persistent `pgdata` volume
- **Claude Runner**: Ephemeral container with Claude Code CLI + gh CLI. Provisioned per skill execution, destroyed after completion.
- **Reverse proxy**: Coolify handles TLS termination + domain routing

## Container Images

### API (`infra/docker/Dockerfile.api`)

| Stage | Base | Purpose |
|-------|------|---------|
| `dev` | `python:3.12-slim` + uv | Hot-reload development (source volumes mounted) |
| `production` | `python:3.12-slim` + uv | Migrations + uvicorn (no dev deps, no reload) |

Production entrypoint:
```bash
sh -c "uv run alembic upgrade head && uv run uvicorn helprs.main:app --host 0.0.0.0 --port 8000"
```

### Web (`infra/docker/Dockerfile.web`)

| Stage | Base | Purpose |
|-------|------|---------|
| `dev` | `node:22-slim` | Vite dev server |
| `build` | `node:22-slim` | `npm ci && npm run build` -> `/app/dist` |
| `production` | `nginx:alpine` | Serves built assets from build stage |

### Claude Runner (`infra/docker/Dockerfile.claude-runner`) -- Coming in Phase 2

| Layer | Contents |
|-------|----------|
| Base | Minimal Linux (alpine or slim) |
| Tools | Claude Code CLI (pinned version), gh CLI, git |
| Entry | Skill-specific entrypoint script |

The claude-runner image will be pre-pulled on production hosts to minimize cold start latency.

## Production Compose (`infra/coolify/docker-compose.prod.yml`)

Key differences from dev:

- No source volume mounts
- No `--reload` flag
- Web on port 80 (nginx) instead of 5173 (Vite)
- DB port not exposed to host
- All services have `restart: unless-stopped`
- API container needs Docker socket access for spawning claude-runner containers

## Environment Configuration

### Required Secrets (production)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres connection string |
| `SECRET_KEY` | JWT signing secret (strong, unique) |
| `GITHUB_APP_ID` | GitHub App numeric ID |
| `GITHUB_APP_PRIVATE_KEY` | GitHub App RSA private key (PEM) |
| `GITHUB_WEBHOOK_SECRET` | Webhook HMAC secret |
| `FERNET_KEY` | Encryption key for stored credentials |
| `FRONTEND_URL` | Frontend origin (e.g., `https://helprs.dev`) |
| `ADMIN_PASSWORD` | SQLAdmin panel password |
| `ENVIRONMENT` | `production` |

### GitHub Actions Secrets

| Secret | Description |
|--------|-------------|
| `GITHUB_TOKEN` | Auto-provided, for GHCR push |
| `COOLIFY_WEBHOOK_URL` | Coolify deployment webhook URL |
| `COOLIFY_TOKEN` | Coolify API bearer token |

## CI/CD Pipeline

### Continuous Integration (`.github/workflows/ci.yml`)

```
Push to any branch / PR to main
       |
       +-- lint-backend  (ruff check + format)
       +-- test-backend  (pytest + Postgres service)
       +-- lint-frontend (eslint)
       +-- test-frontend (vitest)
              |
              v
         build (Docker build both images, no push)
```

### Continuous Deployment (`.github/workflows/deploy.yml`)

```
Push to main
       |
       v
  build-and-push
       |  Login to ghcr.io
       |  Build + push api:latest + api:{sha}
       |  Build + push web:latest + web:{sha}
       |
       v
     deploy (conditional: COOLIFY_WEBHOOK_URL secret exists)
       |  POST to Coolify webhook URL
```

### Image Registry

- Registry: `ghcr.io`
- Dual-tag: `latest` + commit SHA
- *claude-runner image will be added to registry when implemented*

## Health Checks

- **API**: `GET /health` -> `{"status": "ok"}`
- **Database**: `pg_isready -U helprs` (5s interval, 3s timeout, 5 retries)
- **Web**: Nginx serves index.html (standard HTTP 200)

## Container Runner Considerations (Phase 2)

| Concern | Mitigation |
|---------|------------|
| Cold start latency | Pre-pull claude-runner image on all hosts |
| Resource consumption | CPU/memory limits per container, TTL enforcement |
| Concurrent containers | Queue system to limit simultaneous executions |
| Credential security | Ephemeral env vars only, container destroyed after use |
| Docker socket security | API container needs socket access -- evaluate alternatives (Docker-in-Docker, remote Docker host) |

## Rollback

1. Identify last working commit SHA
2. Re-tag images: `docker tag ghcr.io/.../api:{good-sha} ghcr.io/.../api:latest`
3. Push and trigger Coolify redeploy
4. If DB migration needs rollback: `uv run alembic downgrade -1`
