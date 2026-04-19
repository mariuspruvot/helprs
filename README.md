# helPRs

[![CI](https://github.com/mariuspruvot/helprs/actions/workflows/ci.yml/badge.svg)](https://github.com/mariuspruvot/helprs/actions/workflows/ci.yml)

**Pluggable AI skill runner for pull requests.**

helPRs spins up ephemeral Docker containers running [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to execute skills against your PRs -- comprehension quizzes, code reviews, security audits -- and streams results back in real time.

BYOK (Bring Your Own Key): you provide your Claude credentials once. The backend never calls the Claude API -- containers use your credentials natively.

---

## How It Works

```
1. PR opened               2. Pick a skill              3. Get results
   on GitHub                  (or auto-trigger)            streamed live

┌──────────────┐          ┌──────────────────┐         ┌─────────────────┐
│  GitHub App  │ webhook  │   helPRs API     │ docker  │  Claude Code    │
│  sends PR    │────────> │   creates        │───────> │  runs skill     │
│  event       │          │   session        │         │  in container   │
└──────────────┘          └──────────────────┘         └────────┬────────┘
                                                               │ SSE
                                                               v
                                                       ┌─────────────────┐
                                                       │  helPRs UI      │
                                                       │  renders output │
                                                       │  + follow-ups   │
                                                       └─────────────────┘
```

Each container is **ephemeral** -- it clones your repo, runs the skill, streams the output, then self-destructs. No state persists between sessions.

---

## Quick Start

```bash
git clone https://github.com/mariuspruvot/helprs.git
cd helprs
cp .env.example .env
# Fill in .env (see docs/self-hosting.md for details)

docker compose up --build        # API :8000, Web :5173, Postgres :5432
make build-runner                # Build the Claude Code container image
```

Open [http://localhost:5173](http://localhost:5173), authenticate with GitHub, and you're ready to go.

> For production deployment, see the [Self-Hosting Guide](docs/self-hosting.md).

---

## Skills

Skills are pluggable Claude Code agent definitions. Each skill is a self-contained folder with a prompt template, workflow instructions, and configuration.

| Skill | Description | Duration |
|-------|-------------|----------|
| **[challenge-me](skills/challenge-me/)** | Socratic comprehension quiz -- probes whether the PR author truly understands their own changes. Generates 3-5 targeted questions, evaluates answers, and produces a score card. | 5-10 min |

Want to create your own? See [Creating Skills](docs/creating-skills.md).

---

## Architecture

```
apps/api/          FastAPI backend (Python 3.12, uv)
apps/web/          React frontend (Vite, TypeScript, Tailwind 4)
skills/            Claude Code skill definitions (mounted into containers)
infra/docker/      Dockerfiles (api, web, claude-runner)
infra/coolify/     Production docker-compose
docs/              Architecture docs, guides, ADRs
```

The backend is a **container orchestrator**, not an AI host. It receives GitHub webhooks, manages Docker containers, and relays SSE streams. All AI work happens inside ephemeral containers running Claude Code CLI.

For the full picture, see:
- [Architecture Overview](docs/architecture.md) -- system diagram, request flow, module map
- [ADR-001: Container Pivot](docs/adr-001-claude-code-container-pivot.md) -- why this architecture

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, uv |
| Frontend | React 19, Vite, Tailwind CSS v4, Zustand |
| Database | PostgreSQL 16 |
| Containers | Docker, aiodocker, Claude Code CLI |
| Auth | GitHub OAuth, JWT, httpOnly refresh tokens |
| Infra | Docker Compose, Coolify, GHCR |

---

## Documentation

| Document | Audience | Description |
|----------|----------|-------------|
| [Self-Hosting Guide](docs/self-hosting.md) | Operators | Deploy helPRs from scratch |
| [Architecture](docs/architecture.md) | Contributors | System design, data flow, protocols |
| [Creating Skills](docs/creating-skills.md) | Skill authors | Build custom skills |
| [Skill Specification](skills/SKILL_SPEC.md) | Skill authors | Formal spec for skill definitions |
| [Contributing](CONTRIBUTING.md) | Contributors | Dev setup, code style, PR process |
| [ADR-001](docs/adr-001-claude-code-container-pivot.md) | Everyone | Why ephemeral containers |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, code style, and PR guidelines.

```bash
make lint    # Ruff (Python) + ESLint (TypeScript)
make test    # pytest + vitest
```

---

## License

MIT
