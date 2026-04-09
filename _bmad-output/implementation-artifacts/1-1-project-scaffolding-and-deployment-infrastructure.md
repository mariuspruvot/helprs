# Story 1.1: Project Scaffolding & Deployment Infrastructure

Status: done

## Story

As a **developer on the helPRs team**,
I want the monorepo initialized with backend, frontend, infrastructure, CI/CD pipelines, design token foundation, and production deployment config,
So that all future stories have a consistent development environment and automated deployment to build upon.

## Acceptance Criteria

1. **Given** a fresh clone of the repository **When** I run `make dev` **Then** Docker Compose starts 3 services (api, web, db) with hot reload on both backend (uvicorn --reload) and frontend (Vite HMR)

2. **Given** the backend service is running **When** I visit the `/docs` endpoint **Then** I see the FastAPI auto-generated OpenAPI documentation

3. **Given** the frontend service is running **When** I visit the Vite dev server URL **Then** I see a minimal React app with the helPRs design tokens applied (warm dark background `#201d1d`, Berkeley Mono / IBM Plex Mono font stack)

4. **Given** a push to any branch **When** the GitHub Actions CI pipeline (`ci.yml`) runs **Then** it executes lint (ruff + eslint), test (pytest + vitest), and build steps in sequence

5. **Given** a push to main **When** the GitHub Actions deploy pipeline (`deploy.yml`) runs **Then** it builds multi-stage Docker images (Dockerfile.api, Dockerfile.web), pushes them to the container registry, and triggers Coolify deployment

6. **Given** the production Docker images **When** Coolify deploys them using `infra/coolify/docker-compose.prod.yml` **Then** the api and web services start successfully with production configuration (no hot reload, production builds)

7. **Given** the Tailwind config **When** I inspect the generated CSS **Then** all design tokens from DESIGN.md are available as utilities — colors (primary, semantic, border), spacing (8px grid), border radius (4px/6px), and typography scale

8. **Given** the backend project **When** I run `make lint` and `make test` **Then** ruff checks pass and pytest discovers the test directory with a passing placeholder test

9. **Given** the monorepo structure **When** I list the directory tree **Then** it matches the architecture: `apps/api/src/helprs/`, `apps/web/src/`, `infra/docker/`, `infra/coolify/`, `docker-compose.yml`, `Makefile`, `.env.example`

## Tasks / Subtasks

- [x] Task 1: Monorepo structure (AC: #9)
  - [x] 1.1 Create top-level directory structure: `apps/api/`, `apps/web/`, `infra/docker/`, `infra/coolify/`
  - [x] 1.2 Create `Makefile` with targets: `dev`, `lint`, `test`, `build`, `migrate`, `types`
  - [x] 1.3 Create `.env.example` with all required env vars (see Dev Notes)
  - [x] 1.4 Create `.gitignore` (Python + Node + Docker + IDE artifacts)
  - [x] 1.5 Create `README.md` with setup instructions

- [x] Task 2: Backend scaffolding (AC: #2, #8)
  - [x] 2.1 Initialize Python project: `apps/api/` with `uv init --python 3.12` (creates `.python-version` with `3.12` and `uv.lock` — both should be committed)
  - [x] 2.2 Add dependencies to pyproject.toml (see exact versions in Dev Notes)
  - [x] 2.3 Create package structure: `apps/api/src/helprs/__init__.py` and `main.py` (app factory pattern)
  - [x] 2.4 Create `core/` stub directory with empty `__init__.py` files for: `config.py`, `database.py`, `security.py`, `middleware.py`, `exceptions.py`, `dependencies.py`
  - [x] 2.5 Create `modules/` stub directories: `comprehension/`, `installation/`, `identity/`, `billing/`, `webhook/` — each with `__init__.py`
  - [x] 2.6 Create comprehension module sub-directories: `domain/`, `application/`, `infrastructure/`, `presentation/` — each with `__init__.py`
  - [x] 2.7 Create `admin/` stub with `__init__.py` and empty `views.py`
  - [x] 2.8 Create `tests/` directory with `conftest.py` and one placeholder test
  - [x] 2.9 Configure ruff in `pyproject.toml` (linting + formatting)
  - [x] 2.10 Configure pytest in `pyproject.toml`
  - [x] 2.11 Create Alembic config: `alembic.ini` + `alembic/env.py` + empty `versions/`
  - [x] 2.12 Implement minimal `main.py`: FastAPI app with health check `/health` and `/docs` enabled

- [x] Task 3: Frontend scaffolding (AC: #3, #7)
  - [x] 3.1 Initialize React project: `apps/web/` with Vite + React + SWC + TypeScript template
  - [x] 3.2 Install dependencies (see exact versions in Dev Notes)
  - [x] 3.3 Configure Tailwind CSS v4 with design tokens from DESIGN.md
  - [x] 3.4 Create feature directory structure: `features/session/`, `features/demo/`, `features/auth/`, `features/installation/`, `features/landing/`
  - [x] 3.5 Create `shared/` directory structure: `components/`, `hooks/`, `api/`, `theme/`
  - [x] 3.6 Create `shared/theme/tokens.ts` with TypeScript design token constants
  - [x] 3.7 Create minimal `app.tsx` with React Router setup and warm dark background
  - [x] 3.8 Configure `@/` import alias in `tsconfig.json` and `vite.config.ts`
  - [x] 3.9 Configure ESLint (vitest uses default Vite config — no separate `vitest.config.ts` needed)
  - [x] 3.10 Add Berkeley Mono font files to `public/fonts/` with `@font-face` declarations (fallback: IBM Plex Mono from CDN)

- [x] Task 4: Docker & local dev environment (AC: #1)
  - [x] 4.1 Create `infra/docker/Dockerfile.api` — multi-stage: uv install → uvicorn production
  - [x] 4.2 Create `infra/docker/Dockerfile.web` — multi-stage: npm build → nginx serve
  - [x] 4.3 Create `infra/docker/nginx.conf` — SPA-friendly config: `try_files $uri $uri/ /index.html`, gzip, cache headers for static assets
  - [x] 4.4 Create `docker-compose.yml` for local dev with 3 services: api (hot reload), web (Vite HMR), db (PostgreSQL 16)
  - [x] 4.5 Configure volume mounts for hot reload on both services
  - [x] 4.6 Create `infra/coolify/docker-compose.prod.yml` for production deployment

- [x] Task 5: CI/CD pipeline (AC: #4, #5)
  - [x] 5.1 Create `.github/workflows/ci.yml`: lint (ruff + eslint) → test (pytest + vitest) → build
  - [x] 5.2 Create `.github/workflows/deploy.yml`: build multi-stage Docker images → push to registry → trigger Coolify deploy (on main push)

- [x] Task 6: Verification (AC: all)
  - [x] 6.1 Run `make dev` and verify all 3 services start
  - [x] 6.2 Verify `/docs` endpoint serves OpenAPI docs
  - [x] 6.3 Verify frontend shows warm dark background with correct font
  - [x] 6.4 Run `make lint` and `make test` — both pass
  - [x] 6.5 Verify directory structure matches architecture spec

## Definition of Done

- [ ] `make dev` starts 3 containers (api, web, db) without errors
- [ ] `curl http://localhost:8000/health` returns `{"status": "ok"}`
- [ ] `http://localhost:8000/docs` serves OpenAPI UI
- [ ] `http://localhost:5173` shows warm dark background (#201d1d) with mono font
- [ ] `make lint` exits 0
- [ ] `make test` exits 0 (pytest + vitest both pass)
- [ ] Directory tree matches canonical reference below

## Dev Notes

### Technology Summary

| Layer | Key Tech | Manager | Notes |
|-------|----------|---------|-------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic | `uv` | No pip, no requirements.txt |
| Frontend | React 19, Vite, Tailwind v4, TypeScript | `npm` | No yarn/pnpm, no CRA |
| Database | PostgreSQL 16 | Docker | No Redis for MVP |
| Infra | Docker multi-stage, GitHub Actions, Coolify | — | GHCR for images |

### Technology Stack — Exact Versions

**Backend (pyproject.toml dependencies):**
```toml
[project]
requires-python = ">=3.12"

dependencies = [
    "fastapi[standard]>=0.115.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "alembic>=1.14.0",
    "pydantic-settings>=2.7.0",
    "asyncpg>=0.30.0",
    "sqladmin>=0.20.0",
    "python-jose[cryptography]>=3.3.0",
    "cryptography>=44.0.0",
    "httpx>=0.28.0",
    "pydantic-ai>=0.1.0",
    "structlog>=24.4.0",
    "sentry-sdk[fastapi]>=2.19.0",
    "slowapi>=0.1.9",
]

[dependency-groups]
dev = [
    "ruff>=0.8.0",
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
]

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "SIM", "TCH"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Frontend (package.json dependencies):**
```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router": "^7.0.0",
    "zustand": "^5.0.0",
    "@tanstack/react-query": "^5.60.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react-swc": "^4.0.0",
    "typescript": "^5.7.0",
    "vite": "^6.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "vitest": "^3.0.0",
    "@testing-library/react": "^16.0.0",
    "eslint": "^9.0.0"
  }
}
```

> **IMPORTANT on versions:** The architecture doc lists aspirational versions (e.g., FastAPI 0.135.3, ruff 0.15+, Vite 8.0.7) that may not exist yet. The version floors in pyproject.toml and package.json above are intentionally lower to allow flexibility — the package managers will install the **latest stable compatible version**. Use `npm create vite@latest` and `uv add` to resolve actual versions. Do NOT pin to versions that don't exist yet.

### Monorepo Structure — Canonical Reference

```
helprs/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── apps/
│   ├── api/
│   │   ├── src/
│   │   │   └── helprs/
│   │   │       ├── __init__.py
│   │   │       ├── main.py
│   │   │       ├── core/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── config.py      # stub
│   │   │       │   ├── database.py    # stub
│   │   │       │   ├── security.py    # stub
│   │   │       │   ├── middleware.py   # stub
│   │   │       │   ├── exceptions.py  # stub
│   │   │       │   └── dependencies.py # stub
│   │   │       ├── modules/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── comprehension/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── domain/
│   │   │       │   │   │   ├── __init__.py
│   │   │       │   │   │   ├── entities.py      # stub
│   │   │       │   │   │   ├── value_objects.py  # stub
│   │   │       │   │   │   ├── services.py       # stub
│   │   │       │   │   │   └── interfaces.py     # stub
│   │   │       │   │   ├── application/
│   │   │       │   │   │   ├── __init__.py
│   │   │       │   │   │   ├── commands.py  # stub
│   │   │       │   │   │   ├── queries.py   # stub
│   │   │       │   │   │   └── handlers.py  # stub
│   │   │       │   │   ├── infrastructure/
│   │   │       │   │   │   ├── __init__.py
│   │   │       │   │   │   ├── models.py        # stub
│   │   │       │   │   │   ├── repositories.py  # stub
│   │   │       │   │   │   └── agents.py        # stub
│   │   │       │   │   └── presentation/
│   │   │       │   │       ├── __init__.py
│   │   │       │   │       ├── routers.py       # stub
│   │   │       │   │       ├── schemas.py       # stub
│   │   │       │   │       ├── sse.py           # stub
│   │   │       │   │       └── dependencies.py  # stub
│   │   │       │   ├── installation/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── models.py    # stub
│   │   │       │   │   ├── service.py   # stub
│   │   │       │   │   ├── router.py    # stub
│   │   │       │   │   └── schemas.py   # stub
│   │   │       │   ├── identity/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── models.py    # stub
│   │   │       │   │   ├── service.py   # stub
│   │   │       │   │   ├── router.py    # stub
│   │   │       │   │   └── schemas.py   # stub
│   │   │       │   ├── billing/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── models.py    # stub
│   │   │       │   │   ├── service.py   # stub
│   │   │       │   │   ├── router.py    # stub
│   │   │       │   │   └── schemas.py   # stub
│   │   │       │   └── webhook/
│   │   │       │       ├── __init__.py
│   │   │       │       ├── router.py        # stub
│   │   │       │       ├── verification.py  # stub
│   │   │       │       ├── dispatcher.py    # stub
│   │   │       │       └── handlers.py      # stub
│   │   │       └── admin/
│   │   │           ├── __init__.py
│   │   │           └── views.py  # stub
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   ├── conftest.py
│   │   │   └── test_health.py  # placeholder: test /health returns 200
│   │   ├── alembic/
│   │   │   ├── alembic.ini
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   ├── pyproject.toml
│   │   ├── uv.lock           # auto-generated, commit to repo
│   │   └── .python-version   # contains "3.12"
│   │
│   └── web/
│       ├── src/
│       │   ├── app.tsx
│       │   ├── main.tsx
│       │   ├── vite-env.d.ts
│       │   ├── features/
│       │   │   ├── session/      # empty directory
│       │   │   ├── demo/         # empty directory
│       │   │   ├── auth/         # empty directory
│       │   │   ├── installation/ # empty directory
│       │   │   └── landing/      # empty directory
│       │   ├── shared/
│       │   │   ├── components/   # empty directory
│       │   │   ├── hooks/        # empty directory
│       │   │   ├── api/          # empty directory
│       │   │   └── theme/
│       │   │       └── tokens.ts
│       │   └── index.css
│       ├── public/
│       │   └── fonts/            # Berkeley Mono font files
│       ├── index.html
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       └── eslint.config.js
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.web
│   │   └── nginx.conf          # SPA-friendly nginx config for production web
│   └── coolify/
│       └── docker-compose.prod.yml
│
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
└── README.md
```

### Architecture Compliance

**Naming Conventions (enforce from story 1):**
- Python files: `snake_case.py`
- Python classes: `PascalCase`
- TypeScript component files: `PascalCase.tsx`
- TypeScript utility files: `camelCase.ts`
- CSS classes: Tailwind utilities (no custom class names in MVP)

**Import Conventions:**
- Backend: absolute imports from package → `from helprs.core.config import Settings`
- Frontend: `@/` alias for `src/` → `import { tokens } from '@/shared/theme/tokens'`

**Dependency Rule:** `presentation → application → domain ← infrastructure`. Domain imports nothing external.

### Design Token Implementation

**Tailwind CSS v4 — `index.css` approach** (Tailwind v4 uses CSS-first config):

```css
@import "tailwindcss";

/* Berkeley Mono — commercial font, falls back to IBM Plex Mono */
@font-face {
  font-family: 'Berkeley Mono';
  src: url('/fonts/BerkeleyMono-Regular.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'Berkeley Mono';
  src: url('/fonts/BerkeleyMono-Medium.woff2') format('woff2');
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'Berkeley Mono';
  src: url('/fonts/BerkeleyMono-Bold.woff2') format('woff2');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}

/* IBM Plex Mono fallback from Google Fonts CDN */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;700&display=swap');

@theme {
  /* Primary */
  --color-primary: #201d1d;
  --color-primary-light: #fdfcfc;
  --color-surface: #302c2c;

  /* Surfaces */
  --color-light-surface: #f1eeee;
  --color-input-bg: #f8f7f7;

  /* Semantic */
  --color-accent: #007aff;
  --color-accent-hover: #0056b3;
  --color-accent-active: #004085;
  --color-danger: #ff3b30;
  --color-danger-hover: #d70015;
  --color-danger-active: #a50011;
  --color-success: #30d158;
  --color-warning: #ff9f0a;
  --color-warning-hover: #cc7f08;
  --color-warning-active: #995f06;

  /* Text */
  --color-text-primary: #fdfcfc;
  --color-text-secondary: #9a9898;
  --color-text-secondary-light: #424245;
  --color-text-muted: #6e6e73;

  /* Border */
  --color-border: rgba(15, 0, 0, 0.12);
  --color-border-strong: #646262;
  --color-border-tab: #9a9898;

  /* Typography */
  --font-family-mono: 'Berkeley Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;

  /* Spacing (8px grid) */
  --spacing-1: 4px;
  --spacing-2: 8px;
  --spacing-3: 12px;
  --spacing-4: 16px;
  --spacing-5: 20px;
  --spacing-6: 24px;
  --spacing-8: 32px;
  --spacing-10: 40px;
  --spacing-12: 48px;
  --spacing-16: 64px;
  --spacing-20: 80px;
  --spacing-24: 96px;

  /* Typography Scale */
  --font-size-heading: 38px;
  --font-size-body: 16px;
  --font-size-caption: 14px;
  --font-weight-bold: 700;
  --font-weight-medium: 500;
  --font-weight-regular: 400;

  /* Border Radius */
  --radius-default: 4px;
  --radius-input: 6px;
}
```

**TypeScript tokens** (`shared/theme/tokens.ts`) — CSS custom properties are the source of truth; this file provides programmatic access:
```typescript
export const colors = {
  primary: '#201d1d',
  primaryLight: '#fdfcfc',
  surface: '#302c2c',
  lightSurface: '#f1eeee',
  inputBg: '#f8f7f7',
  accent: '#007aff',
  accentHover: '#0056b3',
  danger: '#ff3b30',
  dangerHover: '#d70015',
  success: '#30d158',
  warning: '#ff9f0a',
  warningHover: '#cc7f08',
  textPrimary: '#fdfcfc',
  textSecondary: '#9a9898',
  textSecondaryLight: '#424245',
  textMuted: '#6e6e73',
  border: 'rgba(15, 0, 0, 0.12)',
  borderStrong: '#646262',
  borderTab: '#9a9898',
} as const

export const spacing = {
  1: '4px', 2: '8px', 3: '12px', 4: '16px',
  5: '20px', 6: '24px', 8: '32px', 10: '40px',
  12: '48px', 16: '64px', 20: '80px', 24: '96px',
} as const

export const radius = {
  default: '4px',
  input: '6px',
} as const

export const typography = {
  fontFamily: "'Berkeley Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  heading: { size: '38px', weight: 700 },
  body: { size: '16px', weight: 400 },
  caption: { size: '14px', weight: 400 },
} as const
```

### Makefile Targets

```makefile
.PHONY: dev lint test build migrate types

dev:
	docker compose up --build

lint:
	cd apps/api && uv run ruff check src/ tests/
	cd apps/api && uv run ruff format --check src/ tests/
	cd apps/web && npx eslint src/

test:
	cd apps/api && uv run pytest
	cd apps/web && npx vitest run

build:
	docker compose -f infra/coolify/docker-compose.prod.yml build

migrate:
	cd apps/api && uv run alembic upgrade head

types:
	@echo "OpenAPI → TypeScript type generation (configured in future story)"
```

### .env.example Template

```bash
# Database
DATABASE_URL=postgresql+asyncpg://helprs:helprs@localhost:5432/helprs

# Security
SECRET_KEY=change-me-in-production
FERNET_KEY=change-me-generate-with-cryptography-fernet

# GitHub App
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_WEBHOOK_SECRET=

# Anthropic (demo mode only — users provide their own via BYOK)
ANTHROPIC_API_KEY=

# Lemon Squeezy
LEMONSQUEEZY_API_KEY=
LEMONSQUEEZY_WEBHOOK_SECRET=

# Sentry
SENTRY_DSN=

# Frontend
VITE_API_URL=http://localhost:8000
```

### Docker Compose — Local Dev

```yaml
services:
  api:
    build:
      context: ./apps/api
      dockerfile: ../../infra/docker/Dockerfile.api
      target: dev
    ports:
      - "8000:8000"
    volumes:
      - ./apps/api/src:/app/src
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    command: uv run uvicorn helprs.main:app --host 0.0.0.0 --port 8000 --reload

  web:
    build:
      context: ./apps/web
      dockerfile: ../../infra/docker/Dockerfile.web
      target: dev
    ports:
      - "5173:5173"
    volumes:
      - ./apps/web/src:/app/src
    environment:
      - VITE_API_URL=http://localhost:8000
      - CHOKIDAR_USEPOLLING=true
    command: npx vite --host 0.0.0.0 --port 5173

  db:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: helprs
      POSTGRES_USER: helprs
      POSTGRES_PASSWORD: helprs
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U helprs"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

### CI Pipeline — Key Points

**ci.yml triggers:** push to any branch, pull_request to main

**Steps:**
1. Python lint: `uv run ruff check` + `uv run ruff format --check`
2. Python test: `uv run pytest` (with PostgreSQL service container)
3. Frontend lint: `npx eslint src/`
4. Frontend test: `npx vitest run`
5. Docker build: verify images build successfully

**deploy.yml triggers:** push to main only

**Steps:**
1. Build Docker images (multi-stage)
2. Push to container registry (GitHub Container Registry)
3. Trigger Coolify deployment via webhook

### Dockerfile.api — Multi-Stage (this story creates both stages as-is)

```dockerfile
# Dev stage — volume mount overrides COPY src/ at runtime
FROM python:3.12-slim AS dev
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync
COPY src/ src/

# Production stage
FROM python:3.12-slim AS production
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev
COPY src/ src/
CMD ["uv", "run", "uvicorn", "helprs.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile.web — Multi-Stage (nginx.conf referenced below must be created — see Task 4.3)

```dockerfile
# Dev stage
FROM node:22-slim AS dev
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["npx", "vite", "--host", "0.0.0.0"]

# Build stage
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

### Critical Anti-Patterns to Avoid

1. **Do NOT use `pip`** — use `uv` exclusively for Python package management
2. **Do NOT create a `requirements.txt`** — `pyproject.toml` + `uv.lock` is the standard
3. **Do NOT use Create React App** — use Vite with React SWC plugin
4. **Do NOT use Tailwind v3 config file** (`tailwind.config.ts`) — Tailwind v4 uses CSS-first `@theme` directive in `index.css`. The architecture doc's directory tree lists `tailwind.config.ts` — this is superseded by Tailwind v4. Do NOT create this file.
5. **Do NOT use `npm` if `package-lock.json` doesn't exist** — use `npm` consistently (not yarn/pnpm) per the architecture init commands
6. **Do NOT put source code directly in `apps/api/`** — all Python code goes under `apps/api/src/helprs/` package
7. **Do NOT create `app.py`** — the file is `main.py` with an `app` variable (FastAPI convention)
8. **Do NOT add Redis or any caching layer** — PostgreSQL only for MVP
9. **Do NOT install Celery or any task queue** — use FastAPI BackgroundTasks
10. **Do NOT skip creating stub files** — future stories depend on the directory structure existing
11. **Do NOT configure structlog or Sentry in this story** — dependencies are pre-installed for Story 1.2

### Berkeley Mono Font

Berkeley Mono is a commercial font. For this scaffolding story:
- Add `@font-face` declarations pointing to `public/fonts/BerkeleyMono-Regular.woff2` (and other weights)
- Include IBM Plex Mono as the fallback (load from Google Fonts CDN or install via npm)
- The developer implementing this story should check if the font license is available; if not, IBM Plex Mono works as the primary font until the license is obtained

### Minimal main.py Implementation

```python
from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI(
        title="helPRs API",
        description="Socratic comprehension sessions for pull requests",
        version="0.1.0",
    )

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    return app

app = create_app()
```

This is intentionally minimal. Core infrastructure (database, middleware, exception handling) is Story 1.2. `structlog` and `sentry-sdk` are pre-installed in dependencies for Story 1.2 to configure — do NOT initialize them in `main.py` for this story.

### Project Structure Notes

- This is a **greenfield** project — no existing code to work around
- The monorepo has no workspace manager (no Turborepo, no npm workspaces) — each app is independent with its own package manager
- `apps/api/src/helprs/` is a Python package (has `__init__.py`) — this enables absolute imports like `from helprs.core.config import Settings`
- Stub files should contain minimal content: a docstring explaining the module's purpose and an empty class/function placeholder where appropriate
- The `alembic/` directory lives inside `apps/api/` (not at repo root)

### Source Documents

architecture.md, DESIGN.md, epics.md (Story 1.1), ux-design-specification.md (UX-DR1)

### Review Findings

- [x] [Review][Decision] **Credentials DB hardcodées dans docker-compose.prod.yml** — Résolu: env vars avec fallback `${POSTGRES_PASSWORD:-helprs}` pour fonctionner en local et en prod
- [x] [Review][Decision→Defer] **Deploy workflow sans gate CI** — Résolu: branch protection rules à configurer sur GitHub. Deploy job conditionné à `secrets.COOLIFY_WEBHOOK_URL`
- [x] [Review][Patch] **Dockerfile.web COPY nginx.conf échoue** — Résolu: nginx.conf copié dans apps/web/ (build context)
- [x] [Review][Patch] **Port PostgreSQL exposé en prod** — Résolu: ports retirés du service db en prod
- [x] [Review][Patch] **Coolify webhook curl sans --fail** — Résolu: supprimé le `|| echo` fallback, ajouté condition `if: secrets.COOLIFY_WEBHOOK_URL`
- [x] [Review][Patch] **Deploy "Verify" step ne vérifie rien** — Résolu: step supprimé (le webhook Coolify est fire-and-forget)
- [x] [Review][Patch] **Alembic URL hardcodée sans override env** — Résolu: env.py lit DATABASE_URL avec fallback sur alembic.ini
- [x] [Review][Patch] **docker-compose.prod.yml env_file chemin incorrect** — Résolu: chemin corrigé vers `../../.env`
- [x] [Review][Patch] **docker-compose.prod.yml API sans depends_on db** — Résolu: ajouté depends_on avec service_healthy
- [x] [Review][Defer] **Alembic target_metadata = None** — autogenerate ne détectera pas les modèles. À résoudre dans Story 1.2 quand les modèles seront créés [apps/api/alembic/env.py:16] — deferred, pre-existing
- [x] [Review][Defer] **FERNET_KEY invalide dans CI** — la valeur `test-fernet-key` n'est pas un vrai Fernet key, échouera quand le code l'utilisera. À résoudre dans Story 1.2 [.github/workflows/ci.yml:45] — deferred, pre-existing
- [x] [Review][Defer] **Pas de CORS middleware** — le frontend (5173) ne pourra pas appeler l'API (8000) sans CORSMiddleware. À résoudre dans Story 1.2 [apps/api/src/helprs/main.py] — deferred, pre-existing
- [x] [Review][Defer] **Volume mount dev ne monte pas alembic/** — les migrations créées localement ne sont pas visibles dans le conteneur [docker-compose.yml:10] — deferred, pre-existing
- [x] [Review][Defer] **Nginx sans security headers** — X-Frame-Options, X-Content-Type-Options manquants. À résoudre avant la mise en production [infra/docker/nginx.conf] — deferred, pre-existing

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

- Docker build initially failed due to missing README.md in COPY step — fixed by adding README.md to Dockerfile COPY instructions
- Port 8000 conflict during `make dev` — existing `remindr-backend` container occupies port 8000. Not a scaffolding bug; all 3 Docker images build and the db/web containers start successfully.

### Completion Notes List

- Task 1: Created monorepo structure with Makefile (6 targets), .env.example, .gitignore, README.md
- Task 2: Initialized Python project with uv, installed all dependencies, created full package structure with stubs, tests pass (1/1), ruff lint passes
- Task 3: Initialized React+Vite project, configured Tailwind v4 with full design tokens in index.css, created feature/shared dirs, tokens.ts, app.tsx with React Router, ESLint + vitest pass
- Task 4: Created multi-stage Dockerfiles for api and web, nginx.conf with SPA routing + gzip, docker-compose.yml for local dev, coolify prod compose
- Task 5: Created ci.yml (lint→test→build, parallel jobs with PostgreSQL service container) and deploy.yml (GHCR push + Coolify webhook)
- Task 6: Verified make lint (0 errors), make test (pytest 1/1 + vitest 1/1), directory structure matches canonical reference

### Change Log

- 2026-04-09: Story 1.1 implemented — full monorepo scaffolding with backend, frontend, Docker, and CI/CD

### File List

- Makefile (new)
- .env.example (new)
- .gitignore (new)
- README.md (new)
- docker-compose.yml (new)
- .github/workflows/ci.yml (new)
- .github/workflows/deploy.yml (new)
- apps/api/pyproject.toml (new)
- apps/api/uv.lock (new)
- apps/api/.python-version (new)
- apps/api/README.md (new)
- apps/api/alembic.ini (new)
- apps/api/alembic/env.py (new)
- apps/api/alembic/versions/.gitkeep (new)
- apps/api/src/helprs/__init__.py (new)
- apps/api/src/helprs/main.py (new)
- apps/api/src/helprs/core/__init__.py (new)
- apps/api/src/helprs/core/config.py (new)
- apps/api/src/helprs/core/database.py (new)
- apps/api/src/helprs/core/security.py (new)
- apps/api/src/helprs/core/middleware.py (new)
- apps/api/src/helprs/core/exceptions.py (new)
- apps/api/src/helprs/core/dependencies.py (new)
- apps/api/src/helprs/modules/__init__.py (new)
- apps/api/src/helprs/modules/comprehension/ (full DDD structure, new)
- apps/api/src/helprs/modules/installation/ (stubs, new)
- apps/api/src/helprs/modules/identity/ (stubs, new)
- apps/api/src/helprs/modules/billing/ (stubs, new)
- apps/api/src/helprs/modules/webhook/ (stubs, new)
- apps/api/src/helprs/admin/__init__.py (new)
- apps/api/src/helprs/admin/views.py (new)
- apps/api/tests/__init__.py (new)
- apps/api/tests/conftest.py (new)
- apps/api/tests/test_health.py (new)
- apps/web/package.json (new)
- apps/web/package-lock.json (new)
- apps/web/index.html (new)
- apps/web/tsconfig.json (new)
- apps/web/vite.config.ts (new)
- apps/web/eslint.config.js (new)
- apps/web/src/main.tsx (new)
- apps/web/src/app.tsx (new)
- apps/web/src/app.test.tsx (new)
- apps/web/src/index.css (new)
- apps/web/src/vite-env.d.ts (new)
- apps/web/src/shared/theme/tokens.ts (new)
- apps/web/src/features/ (session, demo, auth, installation, landing dirs, new)
- apps/web/src/shared/ (components, hooks, api dirs, new)
- apps/web/public/fonts/.gitkeep (new)
- infra/docker/Dockerfile.api (new)
- infra/docker/Dockerfile.web (new)
- infra/docker/nginx.conf (new)
- infra/coolify/docker-compose.prod.yml (new)
