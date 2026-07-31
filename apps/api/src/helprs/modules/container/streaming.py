"""Turning container logs into an SSE stream, and persisting it on the way.

Three layers, so each can be used on its own: ``stream_events`` yields raw
tuples, ``stream_output`` formats them as SSE, ``stream_and_persist`` also
writes them to the database.
"""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator, Coroutine
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from helprs.core.database import get_db_context
from helprs.modules.container.docker_client import DockerClient
from helprs.modules.container.models import SessionEvent

logger = structlog.get_logger()

KEEPALIVE_INTERVAL_SECONDS = 15.0
PERSIST_BATCH_SIZE = 10

# Tasks spawned to finish work after a client disconnected. Held so the event
# loop cannot garbage-collect them mid-flight.
_background: set[asyncio.Task] = set()


def spawn_detached(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Run ``coro`` to completion independently of the caller's lifetime."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def stream_events(docker: DockerClient, container_id: str) -> AsyncIterator[tuple[int, str]]:
    """Yield ``(event_id, line)`` from the container's log stream.

    ``(0, "")`` is a keepalive sentinel: no output for
    ``KEEPALIVE_INTERVAL_SECONDS`` (Claude is thinking).

    Never wrap the log iterator in ``asyncio.wait_for``. aiodocker reads a
    multiplexed stream (8-byte header + payload) with ``readexactly``;
    cancelling mid-read desynchronizes the stream position and every later
    event is silently dropped. ``asyncio.wait`` keeps the read task alive
    across keepalives instead.
    """
    event_id = 0
    buffer = ""

    log_iter = docker.container_logs(container_id, follow=True).__aiter__()
    read_task: asyncio.Task[str] | None = None
    try:
        while True:
            if read_task is None:
                read_task = asyncio.ensure_future(log_iter.__anext__())

            done, _ = await asyncio.wait({read_task}, timeout=KEEPALIVE_INTERVAL_SECONDS)

            if not done:
                yield (0, "")
                continue

            try:
                chunk = read_task.result()
            except StopAsyncIteration:
                read_task = None
                break

            read_task = None
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                event_id += 1
                yield (event_id, line)
    finally:
        if read_task is not None:
            read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                await read_task
        # Close the underlying log generator instead of leaving it to the
        # garbage collector, which would run it on an arbitrary later loop.
        if isinstance(log_iter, AsyncGenerator):
            with contextlib.suppress(Exception):
                await log_iter.aclose()

    # Docker may close the stream without a trailing newline, leaving the last
    # event (often the ``result``) sitting in the buffer.
    if buffer.strip():
        yield (event_id + 1, buffer.strip())


async def stream_output(docker: DockerClient, container_id: str, offset: int = 0) -> AsyncIterator[str]:
    """SSE-format the event stream, without persisting anything."""
    async for event_id, line in stream_events(docker, container_id):
        if event_id == 0:
            yield ": keepalive\n\n"
            continue
        if event_id <= offset:
            continue
        yield f"id: {event_id}\ndata: {line}\n\n"


async def _persist(session_id: UUID, batch: list[tuple[int, dict]]) -> None:
    """Insert a batch of events, ignoring ones already stored.

    ``ON CONFLICT DO NOTHING`` makes reconnects and overlapping streams
    idempotent at the storage layer rather than in application code.
    """
    if not batch:
        return
    try:
        async with get_db_context() as db:
            stmt = pg_insert(SessionEvent).values(
                [{"session_id": session_id, "event_id": eid, "data": data} for eid, data in batch]
            )
            await db.execute(stmt.on_conflict_do_nothing(constraint="uq_session_events_session_event"))
    except Exception:
        await logger.aexception("event_persist_failed", session_id=str(session_id), batch_size=len(batch))


async def stream_and_persist(
    docker: DockerClient,
    container_id: str,
    session_id: UUID,
    offset: int = 0,
    batch_size: int = PERSIST_BATCH_SIZE,
) -> AsyncIterator[str]:
    """Stream SSE while batch-writing every event to ``session_events``.

    Events at or below *offset* are skipped for output but still persisted:
    a previous connection may have dropped before its batch was flushed.
    """
    pending: list[tuple[int, dict]] = []

    try:
        async for event_id, line in stream_events(docker, container_id):
            if event_id == 0:
                batch, pending = pending, []
                await _persist(session_id, batch)
                yield ": keepalive\n\n"
                continue

            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                parsed = {"_raw": line}
            pending.append((event_id, parsed))

            if len(pending) >= batch_size:
                batch, pending = pending, []
                await _persist(session_id, batch)

            if event_id <= offset:
                continue
            yield f"id: {event_id}\ndata: {line}\n\n"

        # Stream ended on its own — the last partial batch can be awaited.
        await _persist(session_id, pending)
        pending = []
    finally:
        # Still pending here means the generator was closed mid-iteration by a
        # client disconnect: awaiting would be cancelled with it, so the batch
        # is handed to a detached task instead of being dropped.
        if pending:
            spawn_detached(_persist(session_id, pending))
