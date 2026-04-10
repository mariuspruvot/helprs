"""helPRs API application factory."""

import asyncio
import contextlib
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI

from helprs.core.config import get_settings
from helprs.core.database import (
    clear_session_factory,
    create_engine,
    create_session_factory,
    set_session_factory,
)
from helprs.core.exceptions import DomainError, domain_exception_handler
from helprs.core.middleware import configure_logging, configure_sentry, setup_middleware

logger = structlog.get_logger()

_REPLAY_DISCOVERY_TIMEOUT_SECONDS = 10.0
_REPLAY_CONCURRENCY = 10
_REAPER_INTERVAL_SECONDS = 300


async def _replay_pending_webhook_events(app: FastAPI) -> None:
    """Re-dispatch any webhook_events that survived a crash / are stuck.

    Used by both the lifespan startup path and the periodic reaper loop.
    Bounded by ``LIMIT`` inside ``get_replayable_events`` and a
    ``Semaphore(_REPLAY_CONCURRENCY)`` here so a backlog cannot fan out into
    thousands of concurrent tasks and exhaust the DB pool.

    Failures in the discovery query never block startup — they are logged
    and swallowed. A stuck DB connection is bounded by
    ``_REPLAY_DISCOVERY_TIMEOUT_SECONDS`` via ``asyncio.wait_for``.

    Spawned tasks are tracked on ``app.state.replay_tasks`` so they can be
    awaited on lifespan shutdown (no orphaned ``create_task`` references,
    no tasks cancelled mid-commit by ``engine.dispose()``).
    """
    from helprs.modules.webhook.repository import get_replayable_events
    from helprs.modules.webhook.tasks import process_webhook_event

    session_factory = app.state.session_factory

    async def _discover() -> list:
        async with session_factory() as session:
            return await get_replayable_events(session, older_than_seconds=30)

    try:
        replayable = await asyncio.wait_for(_discover(), timeout=_REPLAY_DISCOVERY_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning("webhook_replay_discovery_timeout", timeout=_REPLAY_DISCOVERY_TIMEOUT_SECONDS)
        return
    except Exception:
        # Never block startup on replay discovery failures.
        logger.exception("webhook_replay_discovery_failed")
        return

    if not replayable:
        return

    logger.info("webhook_replay_started", count=len(replayable))

    semaphore: asyncio.Semaphore = app.state.replay_semaphore
    tracked: set[asyncio.Task] = app.state.replay_tasks

    async def _bounded(event_id) -> None:
        async with semaphore:
            await process_webhook_event(session_factory, event_id)

    for event in replayable:
        task = asyncio.create_task(_bounded(event.id))
        tracked.add(task)
        task.add_done_callback(tracked.discard)


async def _run_webhook_reaper(app: FastAPI, *, interval_seconds: int = _REAPER_INTERVAL_SECONDS) -> None:
    """Periodic reaper that re-runs the replay query on a fixed interval.

    Complements the boot-time replay: a blip mid-run (e.g., `mark_processed`
    commit failure) that leaves a row in ``processing`` would otherwise only
    be recovered on the next restart. With the reaper, recovery happens
    within one ``interval_seconds`` window.

    Cancelled cleanly by the lifespan teardown via ``task.cancel()``.
    """
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await _replay_pending_webhook_events(app)
            except Exception:
                # Never crash the reaper loop — keep going on the next tick.
                logger.exception("webhook_reaper_cycle_failed")
    except asyncio.CancelledError:
        logger.info("webhook_reaper_stopped")
        raise


def create_app() -> FastAPI:
    settings = get_settings()

    # Configure observability
    configure_logging()
    configure_sentry(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage database engine lifecycle, admin setup, and webhook reaper."""
        engine = create_engine()
        reaper_task: asyncio.Task | None = None
        try:
            session_factory = create_session_factory(engine)
            app.state.engine = engine
            app.state.session_factory = session_factory
            # Register the factory for ``get_db_context`` (used by the
            # SSE stream generator for per-question writes outside the
            # request-scoped dep graph — Story 3.3).
            set_session_factory(session_factory)
            app.state.replay_semaphore = asyncio.Semaphore(_REPLAY_CONCURRENCY)
            app.state.replay_tasks = set()

            # Admin panel (needs engine)
            from helprs.admin.views import setup_admin

            setup_admin(app, engine, settings.SECRET_KEY)

            # Crash-replay: any webhook_events still in pending/processing
            # after a grace period are re-dispatched. Fire-and-forget so the
            # server starts serving traffic immediately (AC #2).
            await _replay_pending_webhook_events(app)

            # Periodic reaper: handles rows that get stuck mid-run (e.g.
            # mark_processed commit failure) without waiting for the next
            # restart.
            reaper_task = asyncio.create_task(_run_webhook_reaper(app))

            yield
        finally:
            if reaper_task is not None:
                reaper_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await reaper_task

            # Wait for in-flight replay tasks before disposing the engine so
            # they don't end up writing to a closed pool.
            tracked: set[asyncio.Task] = getattr(app.state, "replay_tasks", set())
            if tracked:
                await asyncio.gather(*tracked, return_exceptions=True)

            clear_session_factory()
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

    from helprs.modules.comprehension.presentation.routers import router as comprehension_router
    from helprs.modules.comprehension.presentation.sse import sse_router as comprehension_sse_router
    from helprs.modules.identity.router import router as identity_router
    from helprs.modules.installation.router import router as installation_router
    from helprs.modules.webhook.router import router as webhook_router

    api_router.include_router(identity_router)
    api_router.include_router(installation_router)
    api_router.include_router(webhook_router)
    api_router.include_router(comprehension_router)
    # Story 3.3: SSE streaming for Socratic question generation. Mounted
    # AFTER the detail router so FastAPI's route matcher considers the
    # more specific ``/{session_id}/stream`` path alongside the existing
    # ``/{session_id}`` detail route.
    api_router.include_router(comprehension_sse_router)

    app.include_router(api_router)

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
