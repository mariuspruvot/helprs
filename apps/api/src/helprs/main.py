"""helPRs API application factory."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from helprs.admin.views import setup_admin
from helprs.core.config import get_settings
from helprs.core.database import (
    clear_session_factory,
    create_engine,
    create_session_factory,
    set_session_factory,
)
from helprs.core.exceptions import DomainError, domain_exception_handler
from helprs.core.middleware import configure_logging, configure_sentry, setup_middleware
from helprs.modules.container import cleanup as container_cleanup
from helprs.modules.container.docker_client import AioDockerClient
from helprs.modules.container.router import router as container_router
from helprs.modules.identity.router import router as identity_router
from helprs.modules.installation.router import router as installation_router
from helprs.modules.webhook.repository import get_replayable_events
from helprs.modules.webhook.router import router as webhook_router
from helprs.modules.webhook.tasks import process_webhook_event

logger = structlog.get_logger()

SessionFactory = async_sessionmaker[AsyncSession]

_REPLAY_DISCOVERY_TIMEOUT_SECONDS = 10.0
_REPLAY_CONCURRENCY = 10
_REAPER_INTERVAL_SECONDS = 300
_CONTAINER_CLEANUP_INTERVAL_SECONDS = 300


async def _replay_pending_webhook_events(app: FastAPI) -> None:
    """Re-dispatch webhook_events that survived a crash or got stuck.

    Runs at startup and on every reaper tick. Discovery is bounded by
    ``asyncio.wait_for`` and never blocks startup; dispatch is bounded by
    ``Semaphore(_REPLAY_CONCURRENCY)`` so a backlog cannot exhaust the DB
    pool. Spawned tasks are tracked on ``app.state.replay_tasks`` so
    shutdown can await them before the engine is disposed.
    """
    session_factory: SessionFactory = app.state.session_factory

    async def _discover() -> list:
        async with session_factory() as session:
            return await get_replayable_events(session, older_than_seconds=30)

    try:
        replayable = await asyncio.wait_for(_discover(), timeout=_REPLAY_DISCOVERY_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning("webhook_replay_discovery_timeout", timeout=_REPLAY_DISCOVERY_TIMEOUT_SECONDS)
        return
    except Exception:
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
    """Re-run the replay query on a fixed interval.

    Complements the boot-time replay: a row left in ``processing`` by a
    mid-run blip would otherwise only be recovered on the next restart.
    """
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await _replay_pending_webhook_events(app)
            except Exception:
                logger.exception("webhook_reaper_cycle_failed")
    except asyncio.CancelledError:
        logger.info("webhook_reaper_stopped")
        raise


async def _run_container_cleanup(
    app: FastAPI,
    *,
    interval_seconds: int = _CONTAINER_CLEANUP_INTERVAL_SECONDS,
) -> None:
    """Destroy Docker containers of sessions past their TTL, on a fixed interval."""
    ttl = get_settings().CONTAINER_TTL_SECONDS
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                docker = AioDockerClient()
                try:
                    async with app.state.session_factory() as db:
                        cleaned = await container_cleanup.cleanup_expired(db, docker, ttl_seconds=ttl)
                        await db.commit()
                        if cleaned:
                            logger.info("container_cleanup_cycle", cleaned=cleaned)
                finally:
                    # Without this the loop leaks one aiohttp session per tick.
                    await docker.close()
            except Exception:
                logger.exception("container_cleanup_cycle_failed")
    except asyncio.CancelledError:
        logger.info("container_cleanup_stopped")
        raise


async def _reconcile_stale_sessions(session_factory: SessionFactory) -> None:
    """Mark sessions left RUNNING/PENDING by a previous run as FAILED."""
    try:
        async with session_factory() as db:
            await container_cleanup.reconcile_stale_sessions(db)
            await db.commit()
    except Exception:
        logger.exception("session_reconciliation_failed")


async def _stop_running_containers(session_factory: SessionFactory) -> None:
    """Stop every container still running before the engine goes away."""
    try:
        docker = AioDockerClient()
        async with session_factory() as db:
            stopped = await container_cleanup.cleanup_all_running(db, docker)
            await db.commit()
            if stopped:
                logger.info("shutdown_containers_stopped", count=stopped)
        await docker.close()
    except Exception:
        logger.exception("shutdown_container_cleanup_failed")


async def _drain_replay_tasks(app: FastAPI) -> None:
    """Await in-flight replay tasks so none writes to a disposed pool."""
    if app.state.replay_tasks:
        await asyncio.gather(*app.state.replay_tasks, return_exceptions=True)


async def _cancel_task(task: asyncio.Task) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Acquire long-lived resources; ``AsyncExitStack`` releases them in reverse order."""
    settings = get_settings()
    async with AsyncExitStack() as stack:
        engine = create_engine()
        stack.push_async_callback(engine.dispose)

        session_factory = create_session_factory(engine)
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.replay_semaphore = asyncio.Semaphore(_REPLAY_CONCURRENCY)
        app.state.replay_tasks = set()

        # get_db_context() (background tasks outside the request dependency
        # graph) resolves sessions through this module-level registry.
        set_session_factory(session_factory)
        stack.callback(clear_session_factory)

        setup_admin(app, engine, settings.SECRET_KEY.get_secret_value())

        await _replay_pending_webhook_events(app)
        await _reconcile_stale_sessions(session_factory)

        stack.push_async_callback(_stop_running_containers, session_factory)
        stack.push_async_callback(_drain_replay_tasks, app)

        for loop in (_run_webhook_reaper(app), _run_container_cleanup(app)):
            stack.push_async_callback(_cancel_task, asyncio.create_task(loop))

        yield


async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Return a 500 the browser can actually read.

    A handler registered for ``Exception`` runs inside Starlette's
    ServerErrorMiddleware, which sits *outside* the user middleware stack — so
    this response never passes through CORSMiddleware. Without the header
    below, an unhandled error reaches the frontend as an opaque CORS failure
    instead of the real status.
    """
    logger.exception("unhandled_exception", path=request.url.path)

    headers: dict[str, str] = {}
    origin = request.headers.get("origin")
    if origin and origin in get_settings().CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"

    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "An unexpected error occurred"},
        headers=headers,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    configure_sentry(settings)

    app = FastAPI(
        title="helPRs API",
        description="AI-powered pull request review assistant",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_exception_handler(DomainError, domain_exception_handler)
    app.add_exception_handler(Exception, _handle_unhandled_exception)
    setup_middleware(app, settings)

    api_router = APIRouter(prefix="/api/v1")
    for router in (container_router, identity_router, installation_router, webhook_router):
        api_router.include_router(router)
    app.include_router(api_router)

    @app.get("/health")
    async def health_check():
        try:
            async with app.state.session_factory() as db:
                await db.execute(text("SELECT 1"))
            return {"status": "ok", "db": "ok"}
        except Exception:
            return JSONResponse(status_code=503, content={"status": "degraded", "db": "unreachable"})

    return app


app = create_app()
