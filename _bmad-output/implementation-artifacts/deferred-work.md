# Deferred Work

## Deferred from: code review of story 1-1-project-scaffolding (2026-04-09)

- **Alembic target_metadata = None** — `env.py` has `target_metadata = None`, so `alembic revision --autogenerate` will produce empty migrations. Fix when models are created in Story 1.2.
- **FERNET_KEY invalide dans CI** — CI uses `test-fernet-key` which is not a valid Fernet key (must be 32 url-safe base64 bytes). Will fail once any code path uses Fernet encryption. Fix in Story 1.2.
- **Pas de CORS middleware** — FastAPI app has no CORSMiddleware. Frontend at :5173 cannot call API at :8000. Fix in Story 1.2 (middleware configuration).
- **Volume mount dev ne monte pas alembic/** — Dev docker-compose only mounts `src/`, so local migration files are not visible in the container. Add `- ./apps/api/alembic:/app/alembic` volume mount.
- **Nginx sans security headers** — Production nginx config missing X-Frame-Options, X-Content-Type-Options, Referrer-Policy, CSP. Add before production launch.
