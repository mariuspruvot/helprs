# Deployment Guide

helPRs runs as a set of Docker containers: an API server, a static frontend, a PostgreSQL database, and ephemeral Claude Runner containers spawned on demand.

## Architecture

```
                         +------------------+
                         |  Reverse Proxy   |
                         |  (Traefik/Caddy) |
                         |  TLS termination |
                         +--------+---------+
                                  |
                    +-------------+-------------+
                    |                           |
          yourdomain.com              api.yourdomain.com
                    |                           |
            +-------v-------+          +--------v--------+
            |     Web       |          |      API        |
            |  (nginx :80)  |          |  (FastAPI :8000)|
            |  Static React |          |  Uvicorn        |
            +---------------+          +---+-------+-----+
                                           |       |
                                     +-----v---+   |
                                     |Postgres  |   |
                                     |  :5432   |   |
                                     +----------+   |
                                                    |
                                          +---------v---------+
                                          |  claude-runner    |
                                          |  (ephemeral,      |
                                          |   spawned per     |
                                          |   session)        |
                                          +-------------------+
```

- **Web**: Nginx serving the built React SPA with `try_files` for client-side routing
- **API**: Uvicorn running FastAPI. Auto-runs Alembic migrations on startup. Spawns ephemeral claude-runner containers via Docker SDK.
- **PostgreSQL 16**: Persistent storage with a `pgdata` volume
- **Claude Runner**: Ephemeral container with Claude Code CLI and `gh` CLI. Created per skill session, destroyed after completion or timeout.
- **Reverse Proxy**: Handles TLS termination and routes traffic to web and API containers. Can be Traefik (Coolify), Caddy, nginx, or an ALB.

## Before You Deploy

Complete the [Self-Hosting Setup](self-hosting.md) first:

1. Create a GitHub App with the required permissions
2. Generate secrets (JWT key, Fernet key, webhook secret)
3. Prepare your environment variables

## Deployment Options

### [Coolify](deploy-coolify.md) — Recommended

Best for single-VPS deployments. Coolify provides a web UI for managing Docker Compose services with automatic TLS via Traefik, GitHub integration for auto-deploys, and a built-in environment variable editor. This is the target we maintain and test against.

**Good for**: Solo developers, small teams, side projects.

### [Docker Compose on a VPS](self-hosting.md#step-3-deploy)

Manual deployment using the production compose file with your own reverse proxy. Covered in the self-hosting guide under Step 3.

**Good for**: Operators comfortable with Docker and reverse proxy configuration.

### Other platforms

Anything that runs `docker compose` with access to the host Docker socket will work (Kubernetes with DinD, AWS ECS with EC2-backed tasks, etc.). None of these are officially supported — expect to adapt the compose file yourself.

## Common Requirements

Regardless of deployment method, you need:

| Requirement | Details |
|-------------|---------|
| **Docker** | 20.10+ with Compose v2 |
| **GitHub App** | Created per [self-hosting guide](self-hosting.md#step-1-create-a-github-app) |
| **Claude credential** | OAuth token via `claude setup-token` or Anthropic API key |
| **Domain** | With DNS pointing to your server (subdomain setup recommended) |
| **Docker socket** | The API container must access `/var/run/docker.sock` to spawn claude-runner containers |

## Health Checks

All deployment methods should verify these endpoints after deploy:

| Service | Check | Expected |
|---------|-------|----------|
| **API** | `GET /health` | `{"status": "ok", "db": "ok"}` (503 with `db: "unreachable"` when DB is down) |
| **Database** | `pg_isready -U helprs` | exit code 0 |
| **Web** | `GET /` | HTTP 200 (serves `index.html`) |
| **TLS** | `curl -I https://yourdomain.com` | valid certificate |

```bash
# Quick verification after deploy
curl -s https://api.yourdomain.com/health | jq .
curl -s -o /dev/null -w "%{http_code}" https://yourdomain.com
```

## CI/CD

### Continuous Integration (`.github/workflows/ci.yml`)

```
Push to any branch / PR to main
       |
       +-- lint-backend  (ruff check + format)
       +-- test-backend  (pytest + Postgres service)
       +-- lint-frontend (eslint)
       +-- test-frontend (vitest)
```

### Continuous Deployment

Images are built locally on the deployment host (not pushed to a registry):

- **Coolify**: auto-deploys on push via GitHub App integration.
- **VPS**: `git pull && docker compose -f infra/coolify/docker-compose.prod.yml up -d --build`.

## Rollback

1. Identify the last working commit SHA
2. Check out that commit on the deployment host
3. Rebuild and restart: `docker compose -f infra/coolify/docker-compose.prod.yml up -d --build`
4. If a database migration needs rollback: `docker compose exec api uv run alembic downgrade -1`
