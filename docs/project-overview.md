# Project Overview — helPRs

> Auto-generated on 2026-04-13 by project documentation workflow (deep scan).

## What is helPRs?

**helPRs** is a Socratic comprehension tool for pull requests. When a PR is opened or synchronized on a GitHub repository with the helPRs GitHub App installed, the system generates AI-driven Socratic questions about the code changes. Developers answer these questions in an interactive chat session, then receive a comprehension score across four dimensions (Depth, Accuracy, Completeness, Insight).

The tool helps teams ensure that PR authors truly understand their changes and that reviewers deeply engage with the code they're reviewing.

## Key Features

- **GitHub App integration**: Automatic session creation on PR open/sync via webhooks
- **BYOK (Bring Your Own Key)**: Users provide their own Anthropic API key — zero vendor lock-in
- **Real-time SSE streaming**: Questions and feedback stream token-by-token
- **Adaptive questioning**: Role-based prompts (author vs reviewer), topic-diverse questions
- **Comprehension scoring**: 4-dimension score card with verdict and growth gaps
- **Privacy-first**: No verbatim question/answer text stored — SHA-256 hashes only
- **Large PR handling**: Smart diff ranking and trimming for PRs with 2000+ lines

## Technology Stack Summary

| Part | Language | Framework | Key Libraries |
|------|----------|-----------|--------------|
| **Backend (api)** | Python 3.12 | FastAPI | SQLAlchemy async, Pydantic AI, httpx, structlog |
| **Frontend (web)** | TypeScript | React 19 | Vite 8, Tailwind 4, Zustand, React Query, react-diff-view |
| **Infrastructure** | Docker | Coolify | GitHub Actions, GHCR, nginx, PostgreSQL 16 |

## Architecture

- **Type**: Monorepo with 3 parts
- **Backend pattern**: Hybrid — simple modules + Clean Architecture (comprehension)
- **Frontend pattern**: Feature-based with collocated state/API
- **Communication**: REST + SSE (12 endpoints)
- **Database**: PostgreSQL 16 with 10 tables, Alembic migrations
- **Auth**: GitHub OAuth -> JWT (15-min access + 7-day refresh cookie)
- **Deployment**: Docker multi-stage builds -> GHCR -> Coolify webhook

## Repository Structure

```
helprs/
├── apps/api/          — FastAPI backend (Python 3.12, uv)
├── apps/web/          — React frontend (Vite, TypeScript)
├── infra/             — Docker configs + Coolify production compose
├── .github/workflows/ — CI (lint+test+build) + CD (GHCR+Coolify)
├── docker-compose.yml — Local development
└── Makefile           — dev, lint, test, build, migrate
```

## Quick Start

```bash
cp .env.example .env   # Configure environment
make dev               # docker compose up --build
# API:  http://localhost:8000
# Web:  http://localhost:5173
# Admin: http://localhost:8000/admin
```
