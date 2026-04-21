.PHONY: dev lint test build build-runner migrate types typecheck

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
	$(MAKE) build-runner

# Builds the claude-runner image used by the API to spawn per-session
# containers. This is a one-time setup per Docker host — the image is not a
# service, it's a runtime dependency referenced by tag in
# helprs/modules/container/service.py (CLAUDE_RUNNER_IMAGE). Re-run this
# target whenever infra/docker/claude-runner/ changes.
build-runner:
	docker build -t claude-runner:latest infra/docker/claude-runner/

migrate:
	cd apps/api && uv run alembic upgrade head

types:
	@echo "OpenAPI → TypeScript type generation (configured in future story)"
