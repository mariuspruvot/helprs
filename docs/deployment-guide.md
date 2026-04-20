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
              +------v------+            +-------v-----+
              |    Web      |            |    API      |
              |   (nginx)   |            |  (FastAPI)  |
              |   :80       |            |   :8000     |
              +-------------+            +------+------+
                                                |
                                     +----------+----------+
                                     |                     |
                              +------v------+     +--------v--------+
                              | PostgreSQL  |     | claude-runner   |
                              |   :5432     |     | (ephemeral,     |
                              +-------------+     |  spawned via    |
                                                  |  Docker socket) |
                                                  +-----------------+
```

## Prerequisites

Before deploying, you need:

1. **A server** with Docker 20.10+ and Docker Compose v2
2. **A domain** with DNS pointing to your server
3. **A GitHub App** configured for helPRs (see [Self-Hosting Setup](self-hosting.md))
4. **A Claude OAuth token** generated via `claude setup-token`

## Deployment Options

| Platform | Complexity | Best for |
|----------|-----------|----------|
| [**Coolify**](deploy-coolify.md) (recommended) | Low | Self-hosters who want a managed experience with auto-deploy, TLS, and a web UI |
| [**Docker Compose**](self-hosting.md#step-3-deploy) | Medium | VPS or bare metal with manual reverse proxy setup |
| [**AWS ECS**](deploy-aws-ecs.md) | High | Teams needing autoscaling, managed database, and AWS integration |

## Common Steps

Regardless of platform, every deployment requires:

1. **Create a GitHub App** -- permissions, webhooks, OAuth callback ([Step-by-step guide](self-hosting.md#step-1-create-a-github-app))
2. **Generate secrets** -- `SECRET_KEY`, `FERNET_KEY`, webhook secret ([Environment config](self-hosting.md#step-2-configure-environment))
3. **Build the claude-runner image** -- not part of docker-compose, built separately
4. **Configure SKILLS_HOST_PATH** -- absolute host path to the `skills/` directory
5. **Set up Claude credentials** -- via the dashboard after first deploy

## Health Checks

| Service | Endpoint | Expected |
|---------|----------|----------|
| API | `GET /health` | `{"status":"ok","db":"ok"}` |
| Database | `pg_isready -U helprs` | exit code 0 |
| Web | `GET /` | HTTP 200 |

## Key Constraints

!!! warning "Docker socket requirement"
    The API container needs access to `/var/run/docker.sock` to spawn claude-runner containers. This rules out fully serverless platforms (e.g., Fargate without EC2). See the [AWS ECS guide](deploy-aws-ecs.md) for workarounds.

!!! warning "Build-time variables"
    `VITE_API_URL` and `VITE_GITHUB_APP_SLUG` are baked into the frontend at build time. Changing them requires rebuilding the web image -- runtime environment variables won't work.
