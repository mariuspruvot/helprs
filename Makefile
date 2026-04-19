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

build-runner:
	docker build -t helprs/claude-runner:latest infra/docker/claude-runner/

migrate:
	cd apps/api && uv run alembic upgrade head

types:
	@echo "OpenAPI → TypeScript type generation (configured in future story)"
