# Project Overview -- helPRs

> Auto-generated on 2026-04-17 (post-pivot rewrite)

## Purpose

helPRs is a pluggable AI skill runner for pull requests. When a PR is opened on a GitHub repository with helPRs installed, it spins up an ephemeral Docker container running Claude Code CLI, executes the selected skill (code review, security audit, challenge quiz, etc.) against the PR, and streams results back to a web UI in real-time.

## How It Works

1. **Install** the helPRs GitHub App on a repository
2. **Configure** Claude credentials in the admin panel (one-time setup per installation)
3. **Open a PR** -- helPRs posts a comment with a session link
4. **Select a skill** -- the user (or auto-trigger) picks a skill to run against the PR
5. **Watch results** -- an ephemeral container clones the repo, runs Claude Code with the skill, and streams output via SSE
6. **Container is destroyed** -- after the skill completes (~5-15 min), the container is removed

## Repository Structure

| Part | Type | Tech Stack | Root | Entry Point |
|------|------|-----------|------|-------------|
| **api** | Backend | Python 3.12, FastAPI, SQLAlchemy async, Docker SDK | `apps/api/` | `src/helprs/main.py` |
| **web** | Frontend | TypeScript 6.0, React 19, Vite 8, Tailwind 4, Zustand | `apps/web/` | `src/app.tsx` |
| **infra** | Infrastructure | Docker, Coolify, GitHub Actions | `infra/` | `docker-compose.yml` |
| **skills** | Skill definitions | Claude Code agents/skills (markdown + CLAUDE.md) | `skills/` | Per-skill folder |

## Architecture Summary

- **Backend**: Container orchestrator + admin + webhook receiver. Flat module architecture (identity, installation, webhook, container). No AI logic in the backend -- all AI runs inside ephemeral containers.
- **Frontend**: Feature-based organization with Zustand stores, React Query for server state, SSE for real-time container output streaming. Skill selection UI. *Coming in Phase 2.*
- **Infrastructure**: Multi-stage Docker builds, CI pipeline, CD via GHCR + Coolify. Ephemeral `claude-runner` container image for skill execution.
- **Database**: PostgreSQL 16 with tables for users, installations, webhooks, and container sessions. Credentials encrypted at rest with Fernet.
- **AI**: Claude Code CLI running inside ephemeral Docker containers. Each skill is a self-contained agent definition mounted as a volume.

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Ephemeral containers | Isolate AI execution, no API key proxying, leverage full Claude Code tool suite |
| Skills as agents | Community-contributable, self-contained skill folders mounted into containers |
| Credential-once model | Users configure Claude credentials once in admin; injected per container as env var |
| SSE passthrough | Container streams output to API, API relays to frontend -- simpler than generating AI responses |
| BYOK model | Open-source friendly: users provide their own Claude credentials |
| gh CLI for PR checkout | Token-based auth, shallow clone + `gh pr checkout` in ~5-10s |

## Architecture Decision Records

- [ADR-001: Pivot to Ephemeral Claude Code Containers](./adr-001-claude-code-container-pivot.md)

## Generated Documentation

| Document | Description |
|----------|-------------|
| [Project Overview](./project-overview.md) | This file |
| [Architecture -- API](./architecture-api.md) | Backend architecture: orchestrator, modules, tech stack |
| [Architecture -- Web](./architecture-web.md) | Frontend architecture, components, state |
| [Architecture -- Infra](./architecture-infra.md) | Docker, CI/CD, container runner |
| [API Contracts](./api-contracts-api.md) | Endpoint reference |
| [Data Models](./data-models-api.md) | Database tables + schemas |
| [Component Inventory](./component-inventory-web.md) | Frontend components + hooks + stores |
| [Source Tree Analysis](./source-tree-analysis.md) | Annotated directory tree |
| [Integration Architecture](./integration-architecture.md) | Data flow: webhook -> container -> frontend |
| [Development Guide](./development-guide.md) | Setup, testing, linting |
| [Deployment Guide](./deployment-guide.md) | Docker, CI/CD, production config |

## Quick Start

```bash
docker compose up --build        # API :8000, Web :5173, Postgres :5432
make lint                        # Ruff + ESLint
make test                        # pytest + vitest
```
