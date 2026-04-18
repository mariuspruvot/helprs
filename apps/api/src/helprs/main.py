"""helPRs API application factory."""

import asyncio
import contextlib
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

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
_CONTAINER_CLEANUP_INTERVAL_SECONDS = 300


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


async def _run_container_cleanup(
    app: FastAPI,
    *,
    interval_seconds: int = _CONTAINER_CLEANUP_INTERVAL_SECONDS,
) -> None:
    """Periodic cleanup of expired container sessions.

    Finds sessions past their TTL and destroys their Docker containers.
    Cancelled cleanly by the lifespan teardown via ``task.cancel()``.
    """
    from helprs.modules.container.service import AioDockerClient, cleanup_expired

    ttl = get_settings().CONTAINER_TTL_SECONDS
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                docker = AioDockerClient()
                async with app.state.session_factory() as db:
                    cleaned = await cleanup_expired(db, docker, ttl_seconds=ttl)
                    await db.commit()
                    if cleaned:
                        logger.info("container_cleanup_cycle", cleaned=cleaned)
            except Exception:
                logger.exception("container_cleanup_cycle_failed")
    except asyncio.CancelledError:
        logger.info("container_cleanup_stopped")
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
        cleanup_task: asyncio.Task | None = None
        try:
            session_factory = create_session_factory(engine)
            app.state.engine = engine
            app.state.session_factory = session_factory
            # Register the factory for ``get_db_context`` (used by
            # background tasks that need DB access outside the request
            # dependency graph).
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

            # Reconcile container sessions left in RUNNING/PENDING by a
            # prior crash — mark them FAILED immediately rather than
            # waiting for TTL expiry.
            try:
                from helprs.modules.container.service import reconcile_stale_sessions

                async with session_factory() as db:
                    await reconcile_stale_sessions(db)
                    await db.commit()
            except Exception:
                logger.exception("session_reconciliation_failed")

            # Periodic reaper: handles rows that get stuck mid-run (e.g.
            # mark_processed commit failure) without waiting for the next
            # restart.
            reaper_task = asyncio.create_task(_run_webhook_reaper(app))
            cleanup_task = asyncio.create_task(_run_container_cleanup(app))

            yield
        finally:
            if cleanup_task is not None:
                cleanup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await cleanup_task

            if reaper_task is not None:
                reaper_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await reaper_task

            # Wait for in-flight replay tasks before disposing the engine so
            # they don't end up writing to a closed pool.
            tracked: set[asyncio.Task] = getattr(app.state, "replay_tasks", set())
            if tracked:
                await asyncio.gather(*tracked, return_exceptions=True)

            # Stop all running containers before shutting down.
            try:
                from helprs.modules.container.service import AioDockerClient, cleanup_all_running

                docker = AioDockerClient()
                async with session_factory() as db:
                    stopped = await cleanup_all_running(db, docker)
                    await db.commit()
                    if stopped:
                        logger.info("shutdown_containers_stopped", count=stopped)
                await docker.close()
            except Exception:
                logger.exception("shutdown_container_cleanup_failed")

            clear_session_factory()
            await engine.dispose()

    app = FastAPI(
        title="helPRs API",
        description="AI-powered pull request review assistant",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Exception handlers
    app.add_exception_handler(DomainError, domain_exception_handler)

    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "An unexpected error occurred"},
        )

    app.add_exception_handler(Exception, _unhandled_exception_handler)

    # Middleware (CORS, logging, rate limiting)
    setup_middleware(app, settings)

    # API router
    api_router = APIRouter(prefix="/api/v1")

    from helprs.modules.container.router import router as container_router
    from helprs.modules.identity.router import router as identity_router
    from helprs.modules.installation.router import router as installation_router
    from helprs.modules.webhook.router import router as webhook_router

    api_router.include_router(container_router)
    api_router.include_router(identity_router)
    api_router.include_router(installation_router)
    api_router.include_router(webhook_router)

    app.include_router(api_router)

    # Health check
    @app.get("/health")
    async def health_check():
        from sqlalchemy import text

        try:
            async with app.state.session_factory() as db:
                await db.execute(text("SELECT 1"))
            return {"status": "ok", "db": "ok"}
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "db": "unreachable"},
            )

    return app


app = create_app()
