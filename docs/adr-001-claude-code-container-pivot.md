# ADR-001: Pivot to Ephemeral Claude Code Containers

> **Status**: Accepted
> **Date**: 2026-04-17
> **Decision makers**: Marius Pruvot (Project Lead)
> **Supersedes**: Current pydantic-ai agent architecture
> **Backup branch**: `pre-pivot/v1`

## Context

helPRs is a Socratic comprehension tool for pull requests. The current architecture uses a FastAPI backend with pydantic-ai agents to generate questions, evaluate answers, and score comprehension. The backend proxies Claude API calls on behalf of users (BYOK model with Fernet-encrypted keys).

### Problems with the current approach

1. **Cost risk**: Proxying API calls means helPRs infrastructure bears the latency and error-handling burden, even though users provide their own keys. At scale, the operational complexity grows linearly with users.
2. **Maintenance burden**: The comprehension module uses a custom DDD layout with pydantic-ai agents, SSE streaming, and complex orchestration code -- all of which must be maintained, tested, and evolved.
3. **Limited capabilities**: The API-based approach limits what agents can do. Claude Code CLI has access to tools (file reading, grep, git operations, shell commands) that API calls cannot replicate without building each capability by hand.
4. **Open-source ambition**: The project aims to become an open-source tool that teams can self-host using their own Claude licenses. A heavy backend with AI orchestration code is harder to maintain as OSS.

## Decision

**Replace the pydantic-ai backend AI layer with ephemeral Docker containers running Claude Code CLI.**

Users provide their Claude credentials once (stored in the admin panel). When a PR event triggers a review, helPRs spins up a short-lived container with Claude Code pre-installed, injects the user's credentials, runs the appropriate skill/agent against the PR, streams results back, and destroys the container.

## New Architecture

```
GitHub PR Event
       |
       v
helPRs API (FastAPI)
  - Receives webhook
  - Posts PR comment with session link
  - Retrieves user's Claude credentials from admin
       |
       v (user clicks link or auto-trigger)
Container Orchestrator
  - Provisions ephemeral Docker container
  - Injects: ANTHROPIC_API_KEY, GITHUB_TOKEN, repo/PR metadata
  - Mounts skill definitions as volume
       |
       v
Ephemeral Container (~5-15 min lifetime)
  +-----------------------------------------+
  | Claude Code CLI                         |
  | - gh repo clone --depth=1 + pr checkout |
  | - Loads assigned skill/agent            |
  | - Executes against PR diff/code         |
  | - Streams output -> helPRs API (SSE)    |
  +-----------------------------------------+
       |
       v
helPRs Frontend (React)
  - Displays results in real-time
  - Skill/agent selection UI
```

### Key design choices

| Choice | Rationale |
|--------|-----------|
| **gh CLI for PR checkout** | Faster than git clone+fetch. Shallow clone + `gh pr checkout` in ~5-10s. Token-based auth, no SSH keys needed in containers. |
| **Skills as agents** | Each skill folder (e.g., `challenge-me`, `code-review`, `security-audit`) is a self-contained agent definition. Mounted into the container as a volume. Claude Code discovers and executes them natively. |
| **Credentials in admin, not per-session** | User configures their Claude key once in the admin panel. Zero friction per PR. Key injected as ephemeral env var -- never persisted in the container. |
| **SSE passthrough** | Container streams Claude Code output to the helPRs API, which relays to the frontend. Same SSE pattern, simpler implementation (passthrough vs. generation). |

### PR fetch strategy (per-skill)

| Strategy | Speed | Use case |
|----------|-------|----------|
| `gh pr diff` only | ~2-3s | Skills that only need the diff (security scan, quick review) |
| Shallow clone + `gh pr checkout` | ~5-10s | Skills that need full file context (challenge-me, comprehension) |
| Full clone | ~30-60s | Avoid -- only if absolutely necessary |

Default: shallow clone + `gh pr checkout`. Optimize per-skill later.

## Consequences

### What changes

| Component | Before | After |
|-----------|--------|-------|
| **AI orchestration** | pydantic-ai agents in Python | Claude Code CLI in containers |
| **Backend role** | AI agent host + API | Container orchestrator + admin + webhook receiver |
| **SSE streaming** | Custom implementation generating AI responses | Passthrough relay from container output |
| **Comprehension module** | DDD layout (domain/application/infrastructure/presentation) | Removed -- replaced by skills |
| **Cost model** | Users provide API key, backend makes calls | Users provide Claude credentials, container uses them directly |
| **Skill system** | N/A | Pluggable skill folders, community-contributable |
| **Dependencies** | pydantic-ai, complex agent code | Docker SDK (or K8s client), gh CLI |

### What stays

- **FastAPI backend**: auth, admin, webhooks, GitHub App integration
- **React frontend**: adapted for skill selection and container result display
- **BYOK model**: users bring their own credentials (now Claude Code credentials instead of API keys)
- **Fernet encryption**: for stored credentials
- **PostgreSQL**: user/installation/session data
- **GitHub App**: webhook delivery, PR comments

### Risks

| Risk | Mitigation |
|------|------------|
| Container cold start latency | Pre-pulled images, shallow clones, diff-only mode for fast skills |
| Credential security in containers | Ephemeral env vars only, container destroyed after use, no volume persistence for secrets |
| Claude Code CLI changes/breaking updates | Pin CLI version in Dockerfile, test on upgrade |
| Resource consumption (many concurrent containers) | Container limits (CPU/memory), queue system, TTL enforcement |
| User needs Claude Code license | Clear documentation, support for API key fallback if needed |

### Removed components (post-cleanup)

- `apps/api/src/helprs/modules/comprehension/` -- entire DDD module
- pydantic-ai dependency
- Custom SSE streaming logic for AI responses
- Agent-related schemas and models in comprehension domain
- Associated tests in `tests/modules/comprehension/`

## Backend simplification

Post-pivot, the backend reduces to:

```
apps/api/src/helprs/
  core/           -- config, database, security, middleware (unchanged)
  modules/
    identity/     -- user auth, GitHub OAuth (unchanged)
    installation/ -- GitHub App installations (unchanged)
    webhook/      -- GitHub webhook receiver (unchanged)
    container/    -- NEW: container orchestration, lifecycle, result relay
  admin/          -- SQLAdmin panel + credential management (extended)
```

## Skill catalog (initial)

| Skill | Description | Fetch strategy |
|-------|-------------|----------------|
| `challenge-me` | Socratic quiz on PR changes -- tests author's understanding | Shallow clone |
| `code-review` | Multi-layer adversarial code review | Shallow clone |
| `security-audit` | Vulnerability scan on the diff | Diff only |
| `doc-generator` | Generate/update impacted documentation | Shallow clone |
| `test-suggester` | Propose missing test cases | Shallow clone |

Community can contribute additional skills via the open-source repository.

## Implementation order

1. Backup current state (`pre-pivot/v1` branch) -- **done**
2. This ADR -- **done**
3. Clean project documentation (CLAUDE.md, docs/) to reflect new architecture
4. Remove comprehension module and pydantic-ai dependency
5. Build container orchestrator module (Docker SDK)
6. Build first skill (challenge-me as Claude Code skill)
7. SSE passthrough from container to frontend
8. Frontend adaptation (skill selection UI)
9. End-to-end test with real PR

## Notes

- The project targets open-source release, designed for self-hosting with existing Claude licenses.
- The skill-as-agent model means the repository itself must be "agent-ready" -- CLAUDE.md and docs must be precise enough for a fresh Claude Code instance to understand the project without prior context.
