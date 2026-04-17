# helPRs -- Project Documentation Index

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Project Overview

- **Type:** Monorepo with 3 parts + skill definitions
- **Primary Language:** Python (backend), TypeScript (frontend)
- **Architecture:** Container orchestrator (backend), feature-based (frontend), ephemeral Claude Code containers (AI)
- **Purpose:** Pluggable AI skill runner for pull requests

## Quick Reference

### api (FastAPI Backend)

- **Type:** backend -- container orchestrator, webhook receiver, admin
- **Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Docker SDK, asyncpg
- **Root:** `apps/api/`
- **Entry Point:** `src/helprs/main.py` -- `create_app()` factory
- **Architecture:** Flat modules (identity, installation, webhook, container)

### web (React Frontend)

- **Type:** web
- **Tech Stack:** TypeScript 6.0, React 19, Vite 8, Tailwind 4, Zustand, React Query
- **Root:** `apps/web/`
- **Entry Point:** `src/app.tsx`
- **Architecture:** Feature-based with collocated state/API

### infra (Docker/Coolify Infrastructure)

- **Type:** infra
- **Tech Stack:** Docker, Coolify, GitHub Actions, Nginx
- **Root:** `infra/`
- **Entry Point:** `docker-compose.yml`
- **Architecture:** Multi-stage Docker builds + CI/CD pipeline + ephemeral claude-runner containers

### skills (Claude Code Skills)

- **Type:** AI agent definitions
- **Root:** `skills/`
- **Architecture:** Self-contained folders, mounted into containers as volumes

## Architecture Decision Records

- [ADR-001: Pivot to Ephemeral Claude Code Containers](./adr-001-claude-code-container-pivot.md)

## Generated Documentation

### Architecture

- [Project Overview](./project-overview.md) -- Purpose, structure, key decisions
- [Architecture -- API](./architecture-api.md) -- Backend as container orchestrator
- [Architecture -- Web](./architecture-web.md) -- Frontend patterns, state management
- [Architecture -- Infra](./architecture-infra.md) -- Docker, CI/CD, container runner
- [Integration Architecture](./integration-architecture.md) -- Data flow: webhook -> container -> frontend

### Technical Reference

- [API Contracts](./api-contracts-api.md) -- Endpoint reference
- [Data Models](./data-models-api.md) -- Database tables + schemas
- [Component Inventory](./component-inventory-web.md) -- Frontend components + hooks + stores
- [Source Tree Analysis](./source-tree-analysis.md) -- Annotated directory tree

### Guides

- [Development Guide](./development-guide.md) -- Prerequisites, setup, testing, code style
- [Deployment Guide](./deployment-guide.md) -- Docker images, CI/CD, production config

## Getting Started

```bash
# Start all services
docker compose up --build
# API at http://localhost:8000, Web at http://localhost:5173

# Run linters
make lint

# Run tests
make test

# Run database migrations
make migrate
```

For detailed setup instructions, see the [Development Guide](./development-guide.md).
