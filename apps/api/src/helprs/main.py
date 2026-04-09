"""helPRs API application factory."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from helprs.core.config import get_settings
from helprs.core.database import create_engine, create_session_factory
from helprs.core.exceptions import DomainError, domain_exception_handler
from helprs.core.middleware import configure_logging, configure_sentry, setup_middleware


def create_app() -> FastAPI:
    settings = get_settings()

    # Configure observability
    configure_logging()
    configure_sentry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage database engine lifecycle and admin setup."""
        engine = create_engine()
        try:
            app.state.engine = engine
            app.state.session_factory = create_session_factory(engine)

            # Admin panel (needs engine)
            from helprs.admin.views import setup_admin

            setup_admin(app, engine, settings.SECRET_KEY)

            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="helPRs API",
        description="Socratic comprehension sessions for pull requests",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Exception handlers
    app.add_exception_handler(DomainError, domain_exception_handler)

    # Middleware (CORS, logging, rate limiting)
    setup_middleware(app, settings)

    # API router
    api_router = APIRouter(prefix="/api/v1")

    from helprs.modules.identity.router import router as identity_router
    from helprs.modules.installation.router import router as installation_router
    from helprs.modules.webhook.router import router as webhook_router

    api_router.include_router(identity_router)
    api_router.include_router(installation_router)
    api_router.include_router(webhook_router)

    app.include_router(api_router)

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
