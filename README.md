# helPRs

Socratic comprehension sessions for pull requests. helPRs helps developers deeply understand code changes by guiding them through interactive question-and-answer sessions on PRs.

## Quick Start

```bash
# Copy environment variables
cp .env.example .env

# Start all services (api, web, db)
make dev
```

Services:
- **API**: http://localhost:8000 (FastAPI + OpenAPI docs at `/docs`)
- **Web**: http://localhost:5173 (React + Vite)
- **DB**: PostgreSQL 16 on port 5432

## Development

```bash
make lint    # Run ruff (backend) + eslint (frontend)
make test    # Run pytest (backend) + vitest (frontend)
make build   # Build production Docker images
make migrate # Run Alembic database migrations
```

## Project Structure

```
helprs/
├── apps/
│   ├── api/          # FastAPI backend (Python 3.12, uv)
│   └── web/          # React frontend (Vite, Tailwind v4)
├── infra/
│   ├── docker/       # Dockerfiles + nginx config
│   └── coolify/      # Production deployment config
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Tech Stack

| Layer    | Technology                          |
|----------|-------------------------------------|
| Backend  | Python 3.12, FastAPI, SQLAlchemy 2  |
| Frontend | React 19, Vite, Tailwind CSS v4     |
| Database | PostgreSQL 16                       |
| Infra    | Docker, GitHub Actions, Coolify     |
