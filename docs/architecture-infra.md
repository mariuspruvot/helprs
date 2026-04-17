# Architecture -- Infrastructure (infra)

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Executive Summary

Docker-based infrastructure with multi-stage builds, GitHub Actions CI/CD, and Coolify for production hosting. Four-service architecture: API (FastAPI), Web (Nginx), PostgreSQL, and ephemeral Claude Runner containers for AI skill execution.

## Service Architecture

```
+-------------------------------------------------------------+
|                     Development                              |
|                                                              |
|  +--------------+  +--------------+  +--------------------+  |
|  | api:8000     |  | web:5173     |  | db:5432            |  |
|  | (uvicorn     |  | (vite dev    |  | (postgres:16       |  |
|  |  --reload)   |  |  server)     |  |  -alpine)          |  |
|  |              |  |              |  |                    |  |
|  | Source vols  |  | Source vols  |  | pgdata volume      |  |
|  +--------------+  +--------------+  +--------------------+  |
|                                                              |
|  Ephemeral: claude-runner containers (spawned on demand)     |
+-------------------------------------------------------------+

+-------------------------------------------------------------+
|                     Production                               |
|                                                              |
|  +--------------+  +--------------+  +--------------------+  |
|  | api:8000     |  | web:80       |  | db (internal)      |  |
|  | (uvicorn,    |  | (nginx,      |  | (postgres:16       |  |
|  |  no reload)  |  |  static)     |  |  -alpine)          |  |
|  |              |  |              |  |                    |  |
|  | No volumes   |  | No volumes   |  | pgdata volume      |  |
|  +--------------+  +--------------+  +--------------------+  |
|                                                              |
|  Ephemeral: claude-runner containers (spawned on demand)     |
|  All services: restart: unless-stopped                       |
|  DB port NOT exposed to host                                 |
+-------------------------------------------------------------+
```

## Claude Runner Container (New)

The `claude-runner` is an ephemeral Docker container that executes AI skills against pull requests.

| Aspect | Detail |
|--------|--------|
| Base image | TBD -- minimal image with Claude Code CLI + gh CLI pre-installed |
| Lifetime | ~5-15 minutes per skill execution |
| Provisioned by | API container's container module (Docker SDK) |
| Injected env vars | `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, repo/PR metadata |
| Mounted volumes | Skill definitions from `skills/` directory |
| Output | Streams stdout/results to API via SSE passthrough |
| Cleanup | Destroyed after skill completes or TTL expires |

**PR fetch strategy (per-skill):**

| Strategy | Speed | Use case |
|----------|-------|----------|
| `gh pr diff` only | ~2-3s | Skills that only need the diff (security scan) |
| Shallow clone + `gh pr checkout` | ~5-10s | Skills needing full file context (default) |

## Dockerfiles

### API (`infra/docker/Dockerfile.api`)

| Stage | Base Image | Dependencies | Entry |
|-------|-----------|--------------|-------|
| `dev` | `python:3.12-slim` + uv | Full (including dev) | Override via compose |
| `production` | `python:3.12-slim` + uv | Production only (`--no-dev`) | `alembic upgrade head && uvicorn ...` |

### Web (`infra/docker/Dockerfile.web`)

| Stage | Base Image | Output | Entry |
|-------|-----------|--------|-------|
| `dev` | `node:22-slim` | -- | `npx vite --host 0.0.0.0` |
| `build` | `node:22-slim` | `/app/dist` | -- |
| `production` | `nginx:alpine` | Copies from build | nginx default |

### Claude Runner (`infra/docker/Dockerfile.claude-runner`) -- Coming in Phase 2

Will contain:

- Claude Code CLI (pinned version)
- gh CLI for PR checkout
- Git for shallow clone
- Minimal OS utilities

## Nginx Configuration

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;

    # SPA routing
    try_files $uri $uri/ /index.html;

    # Asset caching (1 year, immutable)
    location /assets/ { expires 1y; Cache-Control: public, immutable; }
    location /fonts/  { expires 1y; Cache-Control: public, immutable; }

    # Gzip (text, css, json, js, xml, svg, min 256b)
    gzip on;
}
```

**No API proxy** -- Coolify/external reverse proxy handles routing to the API container.

## Docker Compose

### Development (`docker-compose.yml`)

| Service | Build Target | Port | Volumes | Key Env |
|---------|-------------|------|---------|---------|
| api | `dev` | 8000 | `src/`, `alembic/` mounted | `DATABASE_URL`, `.env` file |
| web | `dev` | 5173 | `src/` mounted | `VITE_API_URL=http://localhost:8000` |
| db | postgres:16-alpine | 5432 | `pgdata` named volume | `POSTGRES_DB=helprs` |

The API container needs access to the Docker socket to provision claude-runner containers. *Configuration details TBD.*

### Production (`infra/coolify/docker-compose.prod.yml`)

| Difference | Dev | Prod |
|-----------|-----|------|
| Build target | `dev` | `production` |
| Source volumes | Mounted for hot reload | None |
| API command | `--reload` | Dockerfile CMD |
| Web port | 5173 (Vite) | 80 (Nginx) |
| DB port | Exposed (5432) | Internal only |
| Restart | None | `unless-stopped` |

### Override (`docker-compose.override.yml`)

Contains `GITHUB_APP_PRIVATE_KEY` as YAML block scalar -- workaround for docker-compose's inability to handle multi-line values in `.env` files.

## CI/CD Pipeline

### CI (`.github/workflows/ci.yml`)

**Trigger:** All branch pushes + PRs to main

```
+------------------+  +------------------+
|  lint-backend    |  |  lint-frontend   |
|  (ruff check +  |  |  (eslint)        |
|   format)        |  |                  |
+--------+---------+  +--------+---------+
         |                     |
+--------+---------+  +--------+---------+
|  test-backend    |  |  test-frontend   |
|  (pytest +       |  |  (vitest)        |
|   Postgres svc)  |  |                  |
+--------+---------+  +--------+---------+
         |                     |
         +---------+-----------+
                   |
          +--------v---------+
          |     build        |
          |  (Docker build   |
          |   both images)   |
          +------------------+
```

- 4 parallel lint/test jobs -> 1 gated build job
- Backend tests run against Postgres service container
- `astral-sh/setup-uv@v4` for Python, `actions/setup-node@v4` for Node

### CD (`.github/workflows/deploy.yml`)

**Trigger:** Push to main

```
build-and-push:
  +-- Login to ghcr.io (GITHUB_TOKEN)
  +-- Build + push api:latest + api:{sha}
  +-- Build + push web:latest + web:{sha}

deploy: (conditional: COOLIFY_WEBHOOK_URL exists)
  +-- POST to Coolify webhook (Bearer COOLIFY_TOKEN)
```

- Registry: `ghcr.io`
- Dual-tag: `latest` + commit SHA
- Coolify deploy is fire-and-forget (no verification)

*The claude-runner image will be added to the CI/CD pipeline when implemented.*

## Makefile

| Target | Command | Description |
|--------|---------|-------------|
| `dev` | `docker compose up --build` | Start dev environment |
| `lint` | ruff + eslint | Run all linters |
| `test` | pytest + vitest | Run all tests |
| `build` | prod compose build | Build production images |
| `migrate` | `alembic upgrade head` | Run DB migrations |

## Infrastructure Observations

1. **Docker socket access**: API container needs Docker socket to spawn claude-runner containers -- security implications to evaluate
2. **Container resource limits**: claude-runner containers need CPU/memory limits and TTL enforcement to prevent runaway consumption
3. **No Docker layer caching in CI** -- builds don't use BuildKit cache or GHA cache actions
4. **Coolify deploy is fire-and-forget** -- no status check after webhook POST
5. **Migrations on startup** -- API container always runs `alembic upgrade head` before uvicorn
