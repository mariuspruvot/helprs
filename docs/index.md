# helPRs — Project Documentation Index

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## Project Overview

- **Type:** Monorepo with 3 parts
- **Primary Language:** Python (backend), TypeScript (frontend)
- **Architecture:** Hybrid — simple modules + Clean Architecture (backend), feature-based (frontend)
- **Purpose:** Socratic comprehension tool for pull requests

## Quick Reference

### api (FastAPI Backend)

- **Type:** backend
- **Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Pydantic AI, asyncpg
- **Root:** `apps/api/`
- **Entry Point:** `src/helprs/main.py` — `create_app()` factory
- **Architecture:** Hybrid (simple modules + Clean Architecture for comprehension)

### web (React Frontend)

- **Type:** web
- **Tech Stack:** TypeScript 6.0, React 19, Vite 8, Tailwind 4, Zustand, React Query
- **Root:** `apps/web/`
- **Entry Point:** `src/app.tsx`
- **Architecture:** Feature-based with collocated state/API

### infra (Docker/Coolify Infrastructure)

- **Type:** infra
- **Tech Stack:** Docker multi-stage, nginx, PostgreSQL 16, GitHub Actions
- **Root:** `infra/`
- **Entry Point:** `docker-compose.yml`

## Generated Documentation

### Overview & Architecture

- [Project Overview](./project-overview.md)
- [Architecture — Backend (api)](./architecture-api.md)
- [Architecture — Frontend (web)](./architecture-web.md)
- [Architecture — Infrastructure](./architecture-infra.md)
- [Source Tree Analysis](./source-tree-analysis.md)
- [Integration Architecture](./integration-architecture.md)

### API & Data

- [API Contracts — Backend](./api-contracts-api.md)
- [Data Models — Backend](./data-models-api.md)

### Components & UI

- [Component Inventory — Frontend](./component-inventory-web.md)

### Guides

- [Development Guide](./development-guide.md)
- [Deployment Guide](./deployment-guide.md)

### Metadata

- [Project Parts (JSON)](./project-parts.json)

## Existing Documentation

- [README.md](../README.md) — Project root README
- [API README](../apps/api/README.md) — Backend-specific README
- [Design README](../design/README.md) — Design assets
- [CLAUDE.md](../CLAUDE.md) — AI development context and quick start

## Getting Started

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with GitHub App credentials, SECRET_KEY, FERNET_KEY

# 2. Start all services
make dev
# API:  http://localhost:8000
# Web:  http://localhost:5173
# Admin: http://localhost:8000/admin

# 3. Useful commands
make lint     # Ruff + ESLint
make test     # pytest + vitest
make migrate  # Alembic upgrade head
```

For detailed setup: see [Development Guide](./development-guide.md).
For deployment: see [Deployment Guide](./deployment-guide.md).
