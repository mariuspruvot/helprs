# Backlog

Lightweight list of ideas and open design questions to discuss later. Not a roadmap — just a parking lot so nothing gets lost.

---

## PR eligibility — which PRs should actually trigger a session?

**Problem.** Right now every `pull_request.opened` webhook creates a session + posts a PR comment. That's too aggressive: dependabot bumps, drafts, 5-line typos, and massive refactors all get the same treatment, which dilutes the value of challenge-me and spams repos.

**Current state (half-wired).**
- `installation.suppression_labels` exists in DB.
- `PUT /api/v1/installations/{id}/suppression-labels` + UI in `SettingsView.tsx` let users configure labels.
- But `handle_pull_request_opened` in `apps/api/src/helprs/modules/webhook/handlers.py` never reads them → labels have zero effect today.

**Options on the table.**

1. **Denylist + safe defaults (leading candidate).** Run on everything except:
   - `draft: true`
   - `user.type === "Bot"` (dependabot, renovate, etc.)
   - PR has a label from the suppression list
   - Diff size outside `[min_lines, max_lines]` (too small → nothing to quiz on; too big → quiz loses focus)
   - Optional: `base.ref` not in allowed list (e.g. only target `main`)
   - Optional: title prefix heuristic (`chore:`, `docs:`, `deps:`)

2. **Allowlist label.** Only run when PR has e.g. a `helprs` label. Safest, but kills adoption — people forget to label.

3. **Comment trigger.** User posts `/helprs` to start a session. Explicit, familiar pattern (CodeRabbit, Dependabot), but loses the "automatic" pitch.

4. **Repo config file.** `.helprs.yml` with include/exclude patterns. Most flexible, most friction to adopt.

**Open questions.**
- Default denylist values on install? (draft + bots feels safe to ship on by default.)
- Where do size thresholds live — installation settings, skill settings, or both?
- Do we want a "force run" escape hatch (e.g. `/helprs run` comment) even when a PR is filtered out?
- How do we communicate a skip to the user? Silent? PR comment saying "skipped because X"? Log only?

**Next step when picked up.** Map option 1 to a concrete schema (new columns on `installation`, webhook handler changes, UI in `SettingsView.tsx`) and decide default values.

---

## Repo hygiene agent — dead code, dead files, stale docs

**Problem.** Repo will accumulate: unused functions/classes/imports, orphan files that nothing imports anymore, and docs (CLAUDE.md, `docs/*.md`, README) that drift out of sync with the actual code. Keeping all three tight manually is unrealistic. We want an on-demand Claude Code agent that audits and proposes fixes.

**Scope — what the agent should do.**

1. **Dead code analysis.**
   - Python (`apps/api`): run `vulture` with a confidence threshold; cross-check with grep for string-based references before flagging.
   - TypeScript (`apps/web`): run `knip` (or `ts-prune`) for unused exports, unused files, unused deps.
   - Report per-file findings with a suggested action (delete / inline / keep-and-whitelist).

2. **Dead file cleanup.**
   - Files not imported/referenced anywhere → propose deletion.
   - Respect an allowlist of entry points and convention-loaded paths (see risks below).

3. **Doc freshness audit.**
   - Parse all `CLAUDE.md` + `docs/*.md` + `README.md`.
   - For every code reference (file path, symbol, env var, command) → verify it still exists.
   - Flag stale sections (architecture claims, patterns, gotchas) that no longer match the code.
   - Propose concrete edits, don't just list problems.

**Risks / gotchas the agent must respect.**
- **Convention-loaded code looks dead**: alembic migrations, FastAPI routers wired via `include_router`, SQLAdmin views, pytest fixtures, entry points (`main.py`, `create_app`).
- **Dynamic references**: SQLAdmin model registration, skill folders (`skills/*` loaded at runtime), Jinja/React dynamic imports.
- **BYOK / crypto code paths**: may look dead in dev (no real calls) but are prod-critical.
- **Tests**: a test-only helper isn't dead code — scope analysis per-tree (`src/` vs `tests/`).

**Deliverable shape (to discuss).**
- A `.claude/agents/repo-hygiene.md` subagent, invoked on demand (not a hook — too destructive to auto-run).
- Produces a report → proposes a PR branch with deletions + doc edits → human reviews before merge.
- Dry-run mode by default.

**Open questions.**
- One agent doing all three, or three specialized agents (dead-code, dead-files, docs)?
- Where do we store the allowlist of "looks-dead-but-isn't" paths? (Probably `.repo-hygiene.yml` at repo root.)
- Cadence: manual-only, or wired to a `/loop` weekly schedule?
- For docs: do we want the agent to *rewrite* sections, or just flag + suggest? (Rewriting CLAUDE.md unreviewed is dangerous.)

**Why it matters.** CLAUDE.md correctness is load-bearing for this project — the whole architecture assumes "a fresh Claude Code instance can understand the repo from scratch". Stale docs directly degrade that. Same for dead code: the entrypoint + container orchestration surface is already dense, every unused path is one more thing to read before shipping.

**Next step when picked up.** Decide scope (one agent vs three), draft the subagent definition, test on the current repo state to see what's already accumulating.

---

## SQLAdmin in production — rendering + access

**Problem.** SQLAdmin at `/admin` on `api.helprs.tech` doesn't render cleanly in prod — looks like static assets (CSS/JS) aren't being served or loaded. Also no proper auth flow beyond the basic `ADMIN_PASSWORD` env var.

**Likely causes to investigate.**
- **Static assets path**: SQLAdmin mounts its own statics at `/admin/statics/*`. Traefik routing on `api.helprs.tech` needs to pass that through untouched. Check if the path gets rewritten or blocked.
- **Non-root container + file permissions**: prod Dockerfile uses `appuser` with `chown -R appuser:appuser /app`. SQLAdmin statics are inside the installed package (`sqladmin/statics/`) — confirm they're readable by `appuser`.
- **`.dockerignore` exclusions**: we already had a `*.md` vs `README.md` gotcha for `uv sync`. Worth checking nothing similar bites the static files or templates.
- **CORS / cookie domain**: admin session cookie is set on `api.helprs.tech` — might conflict with how we handle cross-subdomain cookies between `helprs.tech` and `api.helprs.tech`.
- **CSP headers** from our middleware: if we set `Content-Security-Policy`, it may block inline styles/scripts SQLAdmin ships.

**What "proper access" should look like.**
- Auth via GitHub OAuth (reuse the existing identity flow) + role check, instead of a shared `ADMIN_PASSWORD`.
- Scoped by a `users.is_superadmin` flag (or similar), not env-var-gated.
- Admin URL ideally on a less guessable path, or IP-allowlisted via Traefik for extra safety.

**Open questions.**
- Keep SQLAdmin or replace with a custom admin surface in the React dashboard? (SQLAdmin is the "superadmin escape hatch" per CLAUDE.md — low effort to keep, but the UX is showing.)
- If kept: worth a dedicated subdomain like `admin.helprs.tech`? Would simplify Traefik rules and cookie scoping.
- Do we need an audit log for admin actions in prod?

**Next step when picked up.** Reproduce on the deployed env — grab browser devtools network tab for `/admin` to see which asset requests fail and with what status. That'll narrow it to Traefik, container, or SQLAdmin config fast.

---

## Fix stuck `RUNNING` sessions (container race)

**Problem.** If a container exits before the SSE stream fully drains, the client disconnects and the generator cancellation in `_event_stream()` skips the post-stream `mark_completed()` call. Result: session stuck as `RUNNING` with 0 persisted events until the 5-minute cleanup task marks it `TIMEOUT`.

**Why it matters.** User-visible (spinner that never resolves for 5 minutes), skews any "session success rate" metric we add later, and the cleanup task is masking the real bug.

**Next step.** Move `mark_completed()` out of the generator happy-path into a `finally` block or a background task triggered from the container module itself (independent of the SSE consumer). Add a regression test that drops the SSE client mid-stream.

---

## Fix flaky dispatcher tests

**Problem.** `test_issues_opened_is_ignored_and_logged` and `test_pull_request_closed_is_ignored` fail in full-suite runs due to structlog `configure_logging()` state contamination from earlier `create_app()` calls. Pass in isolation.

**Why it matters.** Flaky tests are how real regressions slip in — developers learn to ignore the red.

**Next step.** Either (a) reset structlog state in a session-scoped fixture, (b) isolate logging config so `create_app()` doesn't mutate global state, or (c) stop calling `configure_logging()` in tests entirely. Option (b) is the right long-term fix.

---

## Pin `claude-runner` image, add rollback path

**Problem.** `CLAUDE_RUNNER_IMAGE = "claude-runner:latest"` is hard-coded in `container/service.py`. The build-only service trick (`entrypoint: ["/bin/true"]` + `restart: "no"`) is clever but fragile — a broken build on the deploy server bricks every new session with no rollback. One variant (`profiles: [build-only]`) already regressed once.

**Next step.** Tag the image with a git SHA or semver on build, make `CLAUDE_RUNNER_IMAGE` configurable via env, keep N previous tags on the host for rollback. Consider pushing to GHCR so prod doesn't depend on local builds.

---

## Observability — metrics + tracing

**Problem.** Zero observability beyond structlog. With prod traffic on `helprs.tech` + `api.helprs.tech`, there's no visibility into request latency, session success rate, Claude API errors, container start time, or cleanup task lag. Everything is flying blind.

**Minimum viable.**
- `/metrics` Prometheus endpoint (prometheus-fastapi-instrumentator).
- Custom counters/histograms: `sessions_total{status}`, `session_duration_seconds`, `container_start_duration_seconds`, `webhook_events_total{event_type,outcome}`, `claude_turn_duration_seconds`.
- Eventually: OTel traces for the webhook → session create → container start → SSE stream flow.

**Next step.** Add instrumentator + custom metrics, wire a Grafana dashboard in Coolify. ~half a day for the Prometheus side.

---

## Coolify domain persistence — solve at the compose level

**Problem.** Domains set via the Coolify UI get cleared on redeploy/reload. CLAUDE.md workaround is "re-check after each deploy" — that's a manual process smell, not a real fix.

**Next step.** Add Traefik labels directly to the prod compose (`infra/coolify/docker-compose.prod.yml`) so routing is declarative and version-controlled. Stop relying on Coolify's UI state.

---

## Validate skills architecture with a second skill

**Problem.** `challenge-me` is the only skill. The "skills as pluggable agents" architecture (`SKILL_SPEC.md`, mount into container, etc.) is validated at n=1 — we don't actually know what's generic vs what leaks from challenge-me's assumptions.

**Candidates.**
- `pr-summarize` — generate a structured PR description from the diff.
- `security-review` — static-analysis-ish pass looking for OWASP smells.
- `docs-check` — flag missing docstrings on changed public symbols.

**Why it matters.** Finding the friction points in `SKILL_SPEC.md` is way easier with a second skill than by staring at the spec. Also: having ≥2 skills is what makes the `SkillSelector` UI useful instead of decorative.

**Next step.** Pick one (I'd go `pr-summarize` — simplest, most universally useful), build it, note every place where the spec / entrypoint / UI needed accommodating.

---

## Cost attribution for BYOK users

**Problem.** BYOK users burn their own Claude quota but have zero visibility into per-session or per-installation usage. Result events include `total_cost_usd` / `usage.input_tokens` / `usage.output_tokens` / cache tokens — we throw them away.

**What to build.**
- Persist per-session totals (cost, input/output tokens, cache tokens) aggregated from `result` events.
- Surface in the dashboard: per-session in history, per-installation total over a time window.
- Optional: per-installation monthly budget with soft warnings.

**Why it matters.** It's the #1 question a self-hosting user will ask ("how much is this costing me?"). Answering it also unlocks telling the story "helPRs cost $X this month for Y sessions".

**Next step.** Add columns to `container_sessions`, backfill from `session_events` JSONB, add an aggregation endpoint + UI strip on the installation page.
