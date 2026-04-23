.PHONY: dev lint test build build-runner migrate types typecheck hygiene

dev:
	docker compose up --build

lint:
	cd apps/api && uv run ruff check src/ tests/
	cd apps/api && uv run ruff format --check src/ tests/
	cd apps/api && uv run mypy src/
	cd apps/web && npx eslint src/

typecheck:
	cd apps/api && uv run mypy src/

test:
	cd apps/api && uv run pytest
	cd apps/web && npx vitest run

build:
	docker compose -f infra/coolify/docker-compose.prod.yml build

# Rebuild just the claude-runner image. Normally you don't need to call this
# directly — both compose files declare claude-runner as a build-only service,
# so `docker compose up --build` produces the image as a side-effect. This
# shortcut is useful for quick iteration on infra/docker/claude-runner/ without
# touching the API or web services. Image tag must match
# CLAUDE_RUNNER_IMAGE in helprs/modules/container/service.py.
build-runner:
	docker build -t claude-runner:latest infra/docker/claude-runner/

migrate:
	cd apps/api && uv run alembic upgrade head

types:
	@echo "OpenAPI → TypeScript type generation (configured in future story)"

hygiene:
	@echo "Run the repo-hygiene subagent via Claude Code (e.g. 'audit dead code in the repo')."
	@echo "Config: .repo-hygiene.yml  •  Agent: .claude/agents/repo-hygiene.md"
