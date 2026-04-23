# Contributing to helPRs

Thanks for your interest in contributing. This guide covers the dev setup, code standards, and PR process.

---

## Dev Setup

### Prerequisites

- Docker and Docker Compose (v2)
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and npm

### Start the stack

```bash
git clone https://github.com/mariuspruvot/helprs.git
cd helprs
cp .env.example .env
# Fill in .env (at minimum: SECRET_KEY, FERNET_KEY, GitHub App credentials)

# Start all services (also builds the claude-runner image as a build-only service)
docker compose up --build      # API :8000, Web :5173, Postgres :5432

# Create test database (once)
docker exec helprs-db-1 psql -U helprs -c "CREATE DATABASE helprs_test;"
```

### Running checks

```bash
make lint        # ruff check + format + mypy (non-strict) + eslint
make typecheck   # mypy only (shortcut for API type-checking)
make test        # pytest (API) + vitest (Web)
```

Or run backend/frontend checks individually:

```bash
# Backend
cd apps/api
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run pytest
uv run pytest tests/modules/identity/     # Single module

# Frontend
cd apps/web
npx eslint src/
npx vitest run
```

---

## Code Style

### Python (backend)

- **Formatter/linter**: ruff (`line-length = 120`, target Python 3.12)
- **Lint rules**: E, F, I, N, UP, B, A, SIM, TCH
- No `Any` types -- use specific types or generics
- No `# noqa` or `# type: ignore` -- fix the code
- No imports inside functions (unless breaking circular imports, with a comment explaining why)
- No `unittest.mock` -- use test doubles

### TypeScript (frontend)

- ESLint with the project's config
- Strict TypeScript

### Both

- No suppression comments. If a rule fires, fix the underlying issue.
- Lint must pass before pushing. `make lint` runs everything.

---

## Testing

### Backend (pytest)

- `asyncio_mode = "auto"` -- no need for `@pytest.mark.asyncio` decorators
- Tests use `AsyncClient` with `ASGITransport` (no real HTTP server)
- `conftest.py` sets environment variables **before** any app imports -- order matters
- Test database: `helprs_test` (create with `docker exec helprs-db-1 psql -U helprs -c "CREATE DATABASE helprs_test;"`)

### Frontend (vitest)

- Components that use Shiki (syntax highlighting) must mock `./shiki` in tests to avoid loading TextMate grammars in jsdom

---

## PR Process

1. **Branch from `main`** using a descriptive name: `feat/skill-selector`, `fix/sse-buffering`
2. **Commit messages**: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
3. **Run `make lint`** before pushing -- CI will fail otherwise
4. **Open a PR** targeting `main`
5. Keep PRs focused -- one feature or fix per PR

---

## Project Structure

Read these to understand the codebase:

- [CLAUDE.md](CLAUDE.md) -- detailed patterns, gotchas, key decisions (aimed at AI agents but useful for humans too)
- [docs/architecture.md](docs/architecture.md) -- system diagram, request flow, module map
- [docs/adr-001-claude-code-container-pivot.md](docs/adr-001-claude-code-container-pivot.md) -- why this architecture

### Module layout

Backend modules are flat -- each module has `router.py`, `service.py`, `models.py`, `schemas.py`:

```
apps/api/src/helprs/modules/
├── identity/        # GitHub OAuth, JWT, user profiles
├── installation/    # GitHub App installations, BYOK config
├── webhook/         # GitHub webhook receiver + dispatcher
└── container/       # Container lifecycle, SSE streaming, FIFO messaging
```

---

## Creating Skills

Skills are the easiest way to contribute. See [docs/creating-skills.md](docs/creating-skills.md) for a walkthrough and [skills/SKILL_SPEC.md](skills/SKILL_SPEC.md) for the formal spec.

---

## Database Migrations

```bash
# Create a new migration
cd apps/api && uv run alembic revision --autogenerate -m "add foo column"

# Apply migrations
make migrate
# or inside Docker:
docker compose exec api uv run alembic upgrade head
```

---

## Questions?

Open an issue on GitHub. Include reproduction steps for bugs.
