# helPRs

Pluggable AI skill runner for pull requests. helPRs spins up ephemeral Docker containers running Claude Code CLI to execute skills (comprehension quizzes, code reviews, security audits) against PRs and streams results back in real time.

**BYOK model** -- users provide their own Claude credentials. The backend never calls the Claude API directly; containers use the credentials natively.

## Quick Start

```bash
# Start all services (API :8000, Web :5173, Postgres :5432)
docker compose up --build

# Run tests
make test

# Lint
make lint
```

## How It Works

1. GitHub PR event hits the webhook receiver
2. API posts a PR comment with a session link
3. User selects a skill (or auto-trigger if configured)
4. Backend spins up an ephemeral Docker container with Claude Code CLI
5. Container runs the skill against the PR
6. Results stream back via SSE passthrough to the frontend
7. Container is destroyed after completion or timeout

## Project Structure

```
apps/api/          -- FastAPI backend (Python 3.12, uv)
apps/web/          -- React frontend (Vite, TypeScript, Tailwind 4)
skills/            -- Claude Code skill definitions
infra/docker/      -- Dockerfiles (api, web, claude-runner)
infra/coolify/     -- Production docker-compose
```

## Tech Stack

| Layer      | Technology                                |
|------------|-------------------------------------------|
| Backend    | Python 3.12, FastAPI, SQLAlchemy 2, uv    |
| Frontend   | React 19, Vite, Tailwind CSS v4, Zustand  |
| Database   | PostgreSQL 16                             |
| Containers | Docker, aiodocker, Claude Code CLI        |
| Infra      | GitHub Actions, Coolify, GHCR             |

## Documentation

- **[PROJECT-STATUS.md](PROJECT-STATUS.md)** -- detailed status, what's built, what's not yet working, roadmap
- **[CLAUDE.md](CLAUDE.md)** -- developer context (quick start, patterns, gotchas)
- **[docs/](docs/)** -- architecture, data models, API contracts, component inventory
- **[docs/adr-001-claude-code-container-pivot.md](docs/adr-001-claude-code-container-pivot.md)** -- architecture decision record for the container pivot
