# helPRs — Documentation Index

helPRs is a pluggable AI skill runner for pull requests. The backend is a container orchestrator that spawns ephemeral Claude Code CLI containers per PR session and streams their output back via SSE.

## Repository layout

```
apps/api/    FastAPI backend (Python 3.12, uv)
apps/web/    React/Vite frontend (TypeScript)
skills/      Claude Code skill definitions (mounted into runner containers)
infra/       Dockerfiles + Coolify production compose
docs/        This documentation
```

## Core documents

### Start here

- [README](../README.md) — one-pager, user-facing.
- [Architecture](architecture.md) — how the system works end to end.
- [ADR-001: Pivot to Ephemeral Claude Code Containers](adr-001-claude-code-container-pivot.md) — why the backend orchestrates containers instead of calling an AI API directly.

### Guides

- [Development Guide](development-guide.md) — prerequisites, local setup, testing, code style.
- [Self-Hosting Guide](self-hosting.md) — zero-to-deployed walkthrough.
- [Deployment Guide](deployment-guide.md) — deployment targets and CI/CD overview.
- [Coolify Deployment](deploy-coolify.md) — step-by-step on the production target we maintain.
- [Creating Skills](creating-skills.md) — how to write a new skill (see also `skills/SKILL_SPEC.md`).

### Technical reference

- [API Contracts](api-contracts-api.md) — REST endpoint reference.
- [Data Models](data-models-api.md) — database tables + Pydantic schemas.
- [Component Inventory](component-inventory-web.md) — frontend components, routes, shared primitives.

### Planning

- [Backlog](backlog.md) — open work items.

## Getting started

```bash
docker compose up --build        # API :8000, Web :5173, Postgres :5432
make lint                        # ruff + mypy + eslint
make test                        # pytest + vitest
make migrate                     # alembic upgrade head
```

See the [Development Guide](development-guide.md) for the full setup flow.
