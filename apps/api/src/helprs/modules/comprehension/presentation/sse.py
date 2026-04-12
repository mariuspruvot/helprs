"""Server-Sent Events streaming for comprehension sessions.

Story 3.3 introduced ``GET /api/v1/sessions/{session_id}/stream`` —
a long-lived SSE that streams Socratic questions one token at a time.

Story 3.4 adds ``POST /api/v1/sessions/{session_id}/answers`` — also
SSE-shaped — and refactors the GET stream to PAUSE between questions
until the corresponding answer arrives. The two endpoints are wired
together via ``answer_pubsub`` (per-session in-memory question-text
registry) + the ``answers`` table acting as the single source of
truth for "how many answers has this session received". The GET
stream's loop body is now:

  1. Generate question N (stream tokens, persist hash, emit ``event: question``).
  2. Stash the verbatim text in ``answer_pubsub`` so the POST handler
     can find it again.
  3. Poll ``count_answers(session_id)`` every 500 ms until it reaches
     N, with a 30-min ceiling and a periodic disconnect probe.
  4. Once N answers are recorded, advance to question N+1.

Story 3.4 D1 (code-review decision, 2026-04-11): the previous
``asyncio.Event`` signalling mechanism was replaced with the polling
approach above. The event was a cache that could lie — if the POST
handler signalled before the GET had run ``get_or_create_answer_signal``
+ ``clear()``, the signal was wiped and the GET blocked until the
30-minute timeout. Polling the DB eliminates the race AND makes the
endpoint multi-worker-safe for free (the ``answers`` table is shared
across replicas). Trade-off: ~250 ms average wake latency, which is
negligible next to the LLM streaming cost.

Architecture rules (unchanged from Story 3.3):

* **DB phase / HTTP phase split.** Per-question writes use
  ``get_db_context`` (a fresh short-lived session). The POST endpoint
  follows the same pattern: load session + persist answer in the
  request-scoped ``db``, then snapshot all locals before defining the
  generator that streams feedback.
* **Zero-retention BYOK.** The decrypted API key flows as an argument
  into the LLM provider methods and is dropped at function exit.
* **Hash-only persistence.** Both questions and answers persist only
  the SHA-256 ``text_hash`` — no verbatim ``text`` column anywhere.
* **Manual SSE framing.** ``_sse_frame`` writes ``event: / data: / \\n\\n``
  bytes directly. No ``sse-starlette`` dep.
"""

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from helprs.core.database import get_db_context
from helprs.core.dependencies import GetSettings, get_current_user
from helprs.core.exceptions import ConflictError, DomainValidationError, NotFoundError
from helprs.core.middleware import limiter
from helprs.modules.comprehension.application.handlers import GetSessionHandler
from helprs.modules.comprehension.application.queries import GetSessionQuery
from helprs.modules.comprehension.domain.value_objects import SessionStatus, Topic
from helprs.modules.comprehension.infrastructure.agents import PRPromptContext, PydanticAILLMProvider
from helprs.modules.comprehension.infrastructure.diff_refs import (
    _LARGE_PR_LINE_THRESHOLD,
    compute_file_stats,
    extract_file_refs,
    select_and_rank_files,
)
from helprs.modules.comprehension.infrastructure.github_diff import fetch_pr_diff
from helprs.modules.comprehension.infrastructure.repositories import SqlAlchemySessionRepository
from helprs.modules.comprehension.presentation.answer_pubsub import (
    clear_session,
    get_answer_text,
    get_feedback_text,
    get_question_text,
    is_feedback_committed,
    mark_feedback_committed,
    stash_answer_text,
    stash_feedback_text,
    stash_question_text,
)
from helprs.modules.comprehension.presentation.dependencies import get_llm_provider
from helprs.modules.comprehension.presentation.schemas import SubmitAnswerRequest
from helprs.modules.installation.service import decrypt_byok_key, get_byok_config

logger = structlog.get_logger()

sse_router = APIRouter(prefix="/sessions", tags=["sessions-sse"])

# 30 minutes — outer ceiling for the GET stream's per-question pause.
# A user who walks away from a tab for longer than this gets the
# ``answer_timeout`` error frame and must refresh.
_ANSWER_TIMEOUT_SECONDS = 1800
# DB-polling interval for the pause-loop. At 500 ms the load is a
# single indexed ``COUNT(*)`` per session — negligible next to the
# LLM streaming cost. Story 3.5 can lower this or add a Redis wake
# hint on top without changing the correctness story.
_ANSWER_POLL_INTERVAL_SECONDS = 0.5


def _sse_frame(event: str, data: dict[str, Any]) -> bytes:
    """Encode a single SSE frame: ``event:`` + ``data:`` + blank line."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


class _AnswerTimeoutError(Exception):
    """Raised by ``_wait_for_answer_count`` when the 30-min ceiling is reached."""


class _ClientDisconnectedError(Exception):
    """Raised by ``_wait_for_answer_count`` when the client goes away."""


async def _wait_for_answer_count(
    *,
    session_id: UUID,
    target: int,
    request: Request,
) -> None:
    """Poll ``count_answers`` AND the feedback-committed signal until
    both reach ``target``.

    The DB is the authoritative source for "is the answer persisted",
    but ``count_answers`` alone is NOT sufficient to gate the
    pause-loop on "advance to Q_next now": the POST /answers endpoint
    commits the ``AnswerModel`` row BEFORE it starts streaming
    feedback (Story 3.4 P2 — so a mid-stream disconnect does not lose
    the user's answer). If the pause-loop only waits on
    ``count_answers``, it unblocks milliseconds after the POST commits
    and starts emitting Q_next tokens while F_current is still being
    streamed on the POST response. The client renders in SSE frame
    order, so the UI becomes Q/A/Q_next/F instead of Q/A/F/Q_next
    (manual QA BLOCKER #4, 2026-04-11).

    v1.3.0 fix: also gate on ``is_feedback_committed(session_id,
    target)`` — the POST's generator sets this flag immediately after
    yielding the authoritative ``feedback`` frame. The DB condition
    still runs first (its rising edge is the common case and is
    cheap), the in-memory flag is checked second; returning requires
    BOTH to hold.

    Raises ``_AnswerTimeoutError`` after ``_ANSWER_TIMEOUT_SECONDS``;
    raises ``_ClientDisconnectedError`` if the client goes away.

    Story 3.4 v1.2.0 (code-review F7): ordering + clock hardening.
    (a) Check ``is_disconnected`` BEFORE the DB poll so a client that
    left does not burn a round-trip per iteration. (b) Use
    ``time.monotonic`` for the deadline so NTP steps / container clock
    drift cannot prematurely expire or indefinitely extend the stream.
    (c) Wrap ``count_answers`` in ``asyncio.wait_for(..., 2.0)`` so a
    pathologically slow DB query cannot hold the pause-loop past the
    30-min ceiling — a slow query is treated like "no progress yet".
    """
    deadline = time.monotonic() + _ANSWER_TIMEOUT_SECONDS
    while True:
        if await request.is_disconnected():
            raise _ClientDisconnectedError
        if time.monotonic() >= deadline:
            raise _AnswerTimeoutError
        try:
            async with get_db_context() as tx:
                current = await asyncio.wait_for(
                    SqlAlchemySessionRepository(tx).count_answers(session_id=session_id),
                    timeout=2.0,
                )
        except TimeoutError:
            # Slow DB poll — treat as "no progress yet" and loop.
            current = -1
        # Both conditions must hold: the row is in the DB AND the POST
        # generator has yielded its ``feedback`` frame (v1.3.0
        # BLOCKER #4). The second check is in-process and cheap.
        if current >= target and is_feedback_committed(session_id, target):
            return
        await asyncio.sleep(_ANSWER_POLL_INTERVAL_SECONDS)


@sse_router.get("/{session_id}/stream")
@limiter.limit("20/minute")
async def stream_session(
    session_id: UUID,
    request: Request,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
    llm: PydanticAILLMProvider = Depends(get_llm_provider),  # noqa: B008
) -> StreamingResponse:
    """Stream Socratic questions for the session as Server-Sent Events.

    Wire format:

    * ``event: question_token`` — incremental token appended to the
      current question. ``data: {question_id, token, number, total}``.
    * ``event: question`` — complete question (all tokens accumulated,
      persisted, file refs extracted). ``data: {question_id, text,
      number, total, file_refs}``.
    * ``event: done`` — emitted once after the last question.
      ``data: {session_id, question_count}``.
    * ``event: error`` — emitted on LLM / httpx failure before close.
      ``data: {error, message, retryable}``.

    Story 3.4 change: between each question, the loop pauses until
    the ``answers`` table has the matching row (polled via
    ``count_answers`` every ``_ANSWER_POLL_INTERVAL_SECONDS``). The
    starting question number is computed from ``count_answers + 1``
    so reopening a session whose first N questions are all answered
    correctly resumes at N+1 (closes the deferred bug from Story
    3-3 manual QA).
    """
    # ==================================================================
    # DB phase: load session, authorize, mint token, decrypt BYOK,
    # snapshot already-answered count. Story 3.4 P24 (code-review):
    # the initial load runs in its own short-lived ``get_db_context``
    # instead of pinning a request-scoped FastAPI session for the
    # full 30-minute stream lifetime (connection-pool exhaustion vector).
    # After this block, no DB session is held; per-question writes
    # and the pause-loop's ``count_answers`` polling each open their
    # own fresh session.
    # ==================================================================
    async with get_db_context() as init_db:
        handler = GetSessionHandler(init_db, settings)
        result = await handler.handle(GetSessionQuery(session_id=session_id, requesting_user=user))
        session = result.session
        installation_token = result.installation_token

        # Story 3.4 P1 (code-review): refuse work on terminally-completed
        # sessions. ``PENDING``/``ACTIVE`` both mean "still open"; Epic 4
        # will add the PENDING→ACTIVE→COMPLETED transitions. Until then
        # this is defensive: a COMPLETED session should never accept a
        # new GET stream.
        if session.status == SessionStatus.COMPLETED:
            raise ConflictError(
                "Session is already completed",
                detail={"error": "session_completed", "session_id": str(session_id)},
            )

        byok = await get_byok_config(init_db, session.installation_id)
        if byok is None:
            raise DomainValidationError(f"Installation {session.installation_id} has no BYOK key configured")
        api_key = decrypt_byok_key(byok, settings.FERNET_KEY)

        # Story 3.4: starting number is "first un-answered question"
        # rather than "first un-generated question". When a session is
        # reopened after answering all generated questions,
        # ``count_answers`` matches the existing question count, so the
        # loop generates the next one rather than emitting ``done``
        # immediately.
        repo = SqlAlchemySessionRepository(init_db)
        answered_count = await repo.count_answers(session_id=session_id)
        # Story 3.4 kick-back fix (2026-04-11): also snapshot the
        # already-persisted questions so the loop can REPLAY them
        # instead of regenerating on reconnect. Without this, a second
        # SSE connection would call ``append_question`` for a question
        # number that already exists, and the unique-numbering scheme
        # (``max(number) + 1``) would create a brand-new row at the
        # WRONG number — the regression Project Lead manual QA hit on
        # 2026-04-11 ("pause-loop does not pause; SSE reconnects
        # advance the question cursor"). Closes BLOCKER #1.
        existing_questions = await repo.list_questions(session_id=session_id)
    total = session.total_questions or 5
    # Map number → existing Question (domain entity) for fast replay
    # lookup in the loop body. Local variable, no annotation — domain
    # type isn't needed at runtime here.
    existing_by_number = {q.number: q for q in existing_questions}

    # Snapshot session metadata into plain locals so the generator
    # does not lazy-load ORM attributes after the DB scope is gone.
    repo_owner = session.repo_owner
    repo_name = session.repo_name
    pr_number = session.pr_number
    pr_title = session.pr_title  # Story 3.5: feeds into PRPromptContext
    session_role = session.role
    session_id_str = str(session_id)

    # ==================================================================
    # HTTP / STREAM phase
    # ==================================================================
    async def generator() -> AsyncIterator[bytes]:
        structlog.contextvars.bind_contextvars(session_id=session_id_str)
        try:
            diff = await fetch_pr_diff(
                owner=repo_owner,
                repo=repo_name,
                pr_number=pr_number,
                installation_token=installation_token,
            )

            # Story 3.5 (AC #7): compute per-file stats from the fetched
            # diff. For huge PRs (>= 2000 lines) call ``select_and_rank_files``
            # to trim the diff body to the top-ranked files while
            # preserving the **full** stats list for the prompt (so the
            # LLM knows about files that are not in the body).
            file_stats = compute_file_stats(diff)
            total_lines_changed = sum(s.total_lines for s in file_stats)
            if total_lines_changed >= _LARGE_PR_LINE_THRESHOLD:
                diff, file_stats = select_and_rank_files(diff, stats=file_stats)

            pr_metadata = PRPromptContext(
                role=session_role,
                pr_title=pr_title,
                total_lines_changed=total_lines_changed,
                changed_file_count=len(file_stats),
                file_stats=tuple(file_stats),
            )

            # Story 3.4 kick-back fix: hydrate ``previous_texts`` from
            # the in-memory registry for any questions that already
            # exist on this session (e.g. a prior SSE connection
            # committed Q1 before the client reconnected). Best-effort
            # — entries missing from the registry (server restarted)
            # are skipped so the LLM still gets *some* prior context.
            previous_texts: list[str] = []
            for q in existing_questions:
                cached_text = get_question_text(session_id, q.id)
                if cached_text is not None:
                    previous_texts.append(cached_text)

            client_gone = False
            for _loop_number in range(answered_count + 1, total + 1):
                if await request.is_disconnected():
                    await logger.ainfo("sse_stream_client_disconnected", number=_loop_number)
                    return

                # Story 3.4 kick-back fix (BLOCKER #1): if a question
                # already exists at this number, REPLAY it instead of
                # asking the LLM for a new one. The previous code path
                # blindly called ``append_question``, which uses
                # ``max(number) + 1`` and persisted a duplicate row at
                # the wrong number on every reconnect (StrictMode
                # double-mount + Firefox aborts triggered this in
                # 2026-04-11 manual QA). Replaying preserves the
                # invariant "question N is stable across reconnects"
                # and lets the user submit an in-order answer.
                existing = existing_by_number.get(_loop_number)
                if existing is not None:
                    cached_text = get_question_text(session_id, existing.id)
                    if cached_text is None:
                        # Registry is cold (server restart, or the
                        # prior connection ran on a different process).
                        # Surface a documented error so the user
                        # reloads — there is no way to reconstruct
                        # verbatim text from the SHA-256 hash alone.
                        # TODO(story-3.5): out-of-process registry.
                        yield _sse_frame(
                            "error",
                            {
                                "error": "question_text_unavailable_after_restart",
                                "message": (
                                    "This session has questions whose text is no longer in "
                                    "memory. Please refresh the page to regenerate them."
                                ),
                                "retryable": True,
                            },
                        )
                        return

                    file_refs = extract_file_refs(diff, cached_text)
                    # Emit a single ``question_token`` carrying the
                    # full text so the frontend's streaming UI passes
                    # through the same code path as a fresh question
                    # (the client treats one big token + one
                    # ``question`` frame the same as N small tokens).
                    yield _sse_frame(
                        "question_token",
                        {
                            "question_id": str(existing.id),
                            "token": cached_text,
                            "number": _loop_number,
                            "total": total,
                        },
                    )
                    yield _sse_frame(
                        "question",
                        {
                            "question_id": str(existing.id),
                            "text": cached_text,
                            "number": _loop_number,
                            "total": total,
                            "file_refs": file_refs,
                        },
                    )
                    await logger.ainfo(
                        "sse_stream_question_replayed",
                        number=_loop_number,
                        total=total,
                        file_refs_count=len(file_refs),
                    )
                else:
                    question_id = str(uuid.uuid4())
                    parts: list[str] = []
                    async for token in llm.stream_question(
                        pr_diff=diff,
                        pr_metadata=pr_metadata,
                        previous_questions=previous_texts,
                        api_key=api_key,
                    ):
                        if await request.is_disconnected():
                            await logger.ainfo(
                                "sse_stream_client_disconnected_mid_token",
                                number=_loop_number,
                                tokens_streamed=len(parts),
                            )
                            client_gone = True
                            break
                        parts.append(token)
                        yield _sse_frame(
                            "question_token",
                            {
                                "question_id": question_id,
                                "token": token,
                                "number": _loop_number,
                                "total": total,
                            },
                        )

                    if client_gone:
                        return

                    # P11: reject empty LLM output rather than
                    # persisting a row with ``sha256("")``.
                    if not parts:
                        raise RuntimeError("LLM yielded no tokens for question")

                    text = "".join(parts)
                    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    file_refs = extract_file_refs(diff, text)

                    # Fresh short-lived session per commit.
                    async with get_db_context() as tx:
                        persisted = await SqlAlchemySessionRepository(tx).append_question(
                            session_id=session_id,
                            topic=Topic.ARCHITECTURE,  # TODO(story-3.5): topic selection
                            text_hash=text_hash,
                        )

                    # Story 3.4: stash the verbatim question text in
                    # the in-memory registry so the POST answer handler
                    # can resolve it back from ``persisted.id`` AND so
                    # a future reconnect can replay it via the branch
                    # above.
                    stash_question_text(session_id, persisted.id, text)
                    previous_texts.append(text)
                    # Keep the snapshot in sync with the DB so a later
                    # iteration of THIS loop, if it crosses paths with
                    # a number we just persisted (concurrent stream),
                    # also takes the replay branch.
                    existing_by_number[persisted.number] = persisted

                    yield _sse_frame(
                        "question",
                        {
                            "question_id": str(persisted.id),
                            "text": text,
                            "number": persisted.number,
                            "total": total,
                            "file_refs": file_refs,
                        },
                    )
                    await logger.ainfo(
                        "sse_stream_question_committed",
                        number=persisted.number,
                        total=total,
                        file_refs_count=len(file_refs),
                    )

                # Story 3.4 D1: pause-loop via DB polling. Wait until
                # ``count_answers`` reaches the current question's
                # number before advancing. This applies to EVERY
                # iteration, including the last one — spec AC#5 says
                # ``done`` is emitted after "all questions answered",
                # not merely after "all questions generated".
                try:
                    await _wait_for_answer_count(
                        session_id=session_id,
                        target=_loop_number,
                        request=request,
                    )
                except _AnswerTimeoutError:
                    yield _sse_frame(
                        "error",
                        {
                            "error": "answer_timeout",
                            "message": "Session timed out waiting for an answer",
                            "retryable": False,
                        },
                    )
                    return
                except _ClientDisconnectedError:
                    return

            # P9: report the actual persisted count rather than the
            # target ``total``.
            async with get_db_context() as tx:
                actual_count = await SqlAlchemySessionRepository(tx).count_questions(
                    session_id=session_id,
                )

            # Story 4.1: scoring phase. All questions answered — invoke
            # the scoring agent, persist the score, transition session to
            # COMPLETED, and emit the score SSE frame before ``done``.
            yield _sse_frame(
                "scoring",
                {"text": "Computing your comprehension score..."},
            )

            # Collect Q&A pairs from the in-memory registry for the
            # scoring prompt. Each entry is (question_text, answer_text,
            # feedback_text) — ephemeral, never persisted.
            qa_pairs: list[tuple[str, str, str]] = []
            all_question_entities = list(existing_questions)
            for num in range(len(existing_questions) + 1, actual_count + 1):
                q_entity = existing_by_number.get(num)
                if q_entity is not None:
                    all_question_entities.append(q_entity)
            for q in all_question_entities:
                q_text = get_question_text(session_id, q.id)
                a_text = get_answer_text(session_id, q.id)
                f_text = get_feedback_text(session_id, q.id)
                if q_text is not None and a_text is not None:
                    qa_pairs.append((q_text, a_text, f_text or ""))

            try:
                score_entity = await llm.generate_score(
                    session_id=session_id,
                    session_role=session_role,
                    pr_title=pr_title,
                    questions_and_answers=qa_pairs,
                    pr_metadata=pr_metadata,
                    api_key=api_key,
                )

                # Persist score + transition session to COMPLETED
                async with get_db_context() as tx:
                    score_repo = SqlAlchemySessionRepository(tx)
                    await score_repo.persist_score(score=score_entity)
                    # Transition session status to COMPLETED
                    from sqlalchemy import update as sa_update

                    from helprs.modules.comprehension.infrastructure.models import SessionModel

                    await tx.execute(
                        sa_update(SessionModel)
                        .where(SessionModel.id == session_id)
                        .values(status=SessionStatus.COMPLETED.value)
                    )

                yield _sse_frame(
                    "score",
                    {
                        "depth": score_entity.depth,
                        "accuracy": score_entity.accuracy,
                        "completeness": score_entity.completeness,
                        "insight": score_entity.insight,
                        "verdict": score_entity.verdict.value,
                        "gaps": list(score_entity.gap_summary),
                    },
                )
                await logger.ainfo(
                    "sse_stream_score_emitted",
                    verdict=score_entity.verdict.value,
                    depth=score_entity.depth,
                    accuracy=score_entity.accuracy,
                    completeness=score_entity.completeness,
                    insight=score_entity.insight,
                )
            except Exception:
                await logger.aexception("sse_scoring_failed")
                yield _sse_frame(
                    "error",
                    {
                        "error": "scoring_failed",
                        "message": "Score computation failed. Please reload to retry.",
                        "retryable": True,
                    },
                )
                # Do NOT emit "done" — the session is still ACTIVE in
                # the DB (the status update is inside the try block).
                # Omitting "done" lets the frontend reconnect and retry
                # scoring on the next SSE connection.
                return

            yield _sse_frame(
                "done",
                {"session_id": session_id_str, "question_count": actual_count},
            )
            await logger.ainfo("sse_stream_done", question_count=actual_count, total=total)
            # Drop in-memory registries on a clean finish so a long-
            # running uvicorn worker doesn't accumulate state. Done
            # only here so reconnects (which exit early without
            # finishing the loop) keep their question text registry.
            clear_session(session_id)

        except asyncio.CancelledError:
            await logger.ainfo("sse_stream_cancelled")
            raise
        except Exception as exc:
            await logger.aexception("sse_stream_failed")
            yield _sse_frame(
                "error",
                {
                    "error": type(exc).__name__,
                    "message": str(exc),
                    "retryable": True,
                },
            )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ----------------------------------------------------------------------
# Story 3.4: POST /sessions/{id}/answers — SSE-shaped feedback stream
# ----------------------------------------------------------------------


@sse_router.post("/{session_id}/answers")
@limiter.limit("60/minute")
async def submit_answer(
    session_id: UUID,
    request: Request,
    body: SubmitAnswerRequest,
    settings: GetSettings,
    user=Depends(get_current_user),  # noqa: B008
    llm: PydanticAILLMProvider = Depends(get_llm_provider),  # noqa: B008
) -> StreamingResponse:
    """Persist an answer and stream LLM feedback as Server-Sent Events.

    Wire format:

    * ``event: feedback_token`` — incremental token of the feedback
      stream. ``data: {answer_id, question_id, token}``.
    * ``event: feedback`` — authoritative feedback payload after the
      stream completes. ``data: {answer_id, question_id, text, score,
      gaps}``. ``score`` and ``gaps`` are placeholders for Story 4.1
      (``score: null``, ``gaps: []``). Code-link detection is done
      frontend-side from the rendered markdown — the backend no longer
      pre-parses ``(file, line)`` refs from the feedback text.
    * ``event: done`` — final frame, signals close. ``data:
      {question_number, answer_id}``.
    * ``event: error`` — emitted on LLM / httpx failure before close.

    Pre-stream errors (404 / 403 / 422 / 409) are returned as normal
    JSON responses so the frontend's ``fetch`` rejects with an HTTP
    status it can branch on.
    """
    # ==================================================================
    # DB phase — Story 3.4 v1.2.0 (code-review F17): use ``get_db_context``
    # instead of the request-scoped ``DbSession`` dependency so this
    # block holds a SINGLE, short-lived session that commits on clean
    # exit of the ``async with``. The previous implementation mixed
    # ``DbSession`` + an explicit ``await db.commit()`` with the
    # dependency's own commit on generator finish, creating a double-
    # commit path that was fragile under exception flow. Mirrors the
    # pattern already used by ``stream_session`` (P24). Snapshots every
    # DB-derived local before exiting so the generator runs entirely
    # on plain Python values.
    # ==================================================================
    async with get_db_context() as db:
        handler = GetSessionHandler(db, settings)
        result = await handler.handle(GetSessionQuery(session_id=session_id, requesting_user=user))
        session = result.session
        installation_token = result.installation_token

        # Story 3.4 P1: reject answers on terminally-completed sessions.
        if session.status == SessionStatus.COMPLETED:
            raise ConflictError(
                "Session is already completed",
                detail={"error": "session_completed", "session_id": str(session_id)},
            )

        repo = SqlAlchemySessionRepository(db)
        question = await repo.get_question_by_number(session_id=session_id, number=body.question_number)
        if question is None:
            # Map to 404 with a clean error code so the frontend can
            # branch without parsing free-text messages.
            raise NotFoundError(
                "Question not found for this session",
                detail={"error": "question_not_found", "question_number": body.question_number},
            )

        # Story 3.4 P4: enforce in-order answer submission.
        # ``answered_count`` is the monotonic "next expected" question
        # number (1-indexed: answered_count == 0 → expecting Q1,
        # answered_count == 3 → expecting Q4). Out-of-order POSTs break
        # the ``progress`` array semantics and leave holes in the
        # answers table.
        answered_count = await repo.count_answers(session_id=session_id)
        expected_number = answered_count + 1
        if body.question_number != expected_number:
            raise ConflictError(
                "Answer submitted out of order",
                detail={
                    "error": "answer_out_of_order",
                    "question_number": body.question_number,
                    "expected_number": expected_number,
                },
            )

        byok = await get_byok_config(db, session.installation_id)
        if byok is None:
            raise DomainValidationError(f"Installation {session.installation_id} has no BYOK key configured")
        api_key = decrypt_byok_key(byok, settings.FERNET_KEY)

        # Hash the answer text BEFORE persisting. The verbatim text
        # never touches disk; only ``text_hash`` and ``latency_ms``
        # land in the ``answers`` row.
        answer_text = body.text
        text_hash = hashlib.sha256(answer_text.encode("utf-8")).hexdigest()

        # Latency = wall-clock between question commit and answer
        # arrival. ``max(0, ...)`` guards against clock skew (an LLM
        # token committed in microseconds before the POST landed could
        # otherwise yield a negative).
        latency_ms = max(0, int((datetime.now(UTC) - question.created_at).total_seconds() * 1000))

        try:
            answer = await repo.append_answer(
                question_id=question.id,
                text_hash=text_hash,
                latency_ms=latency_ms,
            )
        except DomainValidationError as exc:
            # Translate the unique-constraint violation into 409
            # Conflict with a stable error code. The frontend uses this
            # to show "answer already submitted" without flashing a
            # generic banner.
            raise ConflictError(
                "Answer already submitted for this question",
                detail={
                    "error": "answer_already_submitted",
                    "question_number": body.question_number,
                },
            ) from exc

        # Story 4.1: stash the verbatim answer text for the scoring
        # phase. Same lifecycle as question text — cleared by
        # clear_session.
        stash_answer_text(session_id, question.id, answer_text)

        # Story 3.4: look up the verbatim question text from the
        # in-memory registry. ``None`` means the server restarted
        # between question commit and the POST landing — surface a
        # documented 422 with an error code the frontend can show.
        question_text = get_question_text(session_id, question.id)
        if question_text is None:
            # TODO(story-3.5): properly solve this via session-state
            # replay (LLM-side question regeneration when the registry
            # is cold). For Story 3.4 the user must reload to
            # re-generate the question. Raising here rolls back the
            # just-inserted answer row via get_db_context's rollback,
            # which is the correct behaviour — the stream never starts.
            raise DomainValidationError(
                "Question text is no longer in memory (server restarted?)",
                detail={"error": "question_text_unavailable_after_restart"},
            )

        # Snapshot DB-derived locals into plain Python values so the
        # generator does not touch ``db`` after this block exits. The
        # ``async with`` below commits the answer row on clean exit,
        # meeting spec AC#4 "committed before streaming begins".
        repo_owner = session.repo_owner
        repo_name = session.repo_name
        pr_number = session.pr_number
        session_role = session.role
        session_id_str = str(session_id)
        question_id = question.id
        answer_id_str = str(answer.id)
        question_number = body.question_number
    # <-- get_db_context commits here on clean exit of the async with.

    # ==================================================================
    # HTTP / STREAM phase
    # ==================================================================
    async def generator() -> AsyncIterator[bytes]:
        structlog.contextvars.bind_contextvars(
            session_id=session_id_str,
            question_id=str(question_id),
            answer_id=answer_id_str,
        )
        try:
            diff = await fetch_pr_diff(
                owner=repo_owner,
                repo=repo_name,
                pr_number=pr_number,
                installation_token=installation_token,
            )

            parts: list[str] = []
            async for token in llm.stream_feedback(
                question_text=question_text,
                answer_text=answer_text,
                pr_diff=diff,
                role=session_role,
                api_key=api_key,
            ):
                if await request.is_disconnected():
                    await logger.ainfo(
                        "sse_feedback_client_disconnected_mid_token",
                        tokens_streamed=len(parts),
                    )
                    # Answer is already persisted; nothing to roll back.
                    # Story 3.4 v1.3.0 (BLOCKER #4 edge case): mark the
                    # feedback committed so the GET pause-loop is free
                    # to advance if another client reopens the stream.
                    # Without this, an abandoned mid-stream POST would
                    # deadlock the session until the 30-min timeout.
                    mark_feedback_committed(session_id, question_number)
                    return
                parts.append(token)
                yield _sse_frame(
                    "feedback_token",
                    {
                        "answer_id": answer_id_str,
                        "question_id": str(question_id),
                        "token": token,
                    },
                )

            # AC #14: empty LLM response is NOT an error — substitute
            # a placeholder string and continue. The answer row is
            # already committed; the user sees a "skipped" message and
            # the GET stream advances to the next question.
            if not parts:
                full_text = "Skipped a question that didn't generate properly. The next question will appear shortly."
            else:
                full_text = "".join(parts)

            # Story 4.1: stash feedback text for the scoring phase.
            stash_feedback_text(session_id, question_id, full_text)

            yield _sse_frame(
                "feedback",
                {
                    "answer_id": answer_id_str,
                    "question_id": str(question_id),
                    "text": full_text,
                    "score": None,  # Story 4.1: session-level scoring, not per-question
                    "gaps": [],  # Story 4.1: gaps are session-level, not per-feedback
                },
            )

            # Story 3.4 v1.3.0 (BLOCKER #4): signal the pause-loop that
            # THIS question's feedback is now fully on the wire. The GET
            # stream's ``_wait_for_answer_count`` gates advancement on
            # this flag AND on ``count_answers``, so Q_next will not
            # start streaming until F_current has been yielded in full.
            # Ordering is load-bearing: mark AFTER the yield, BEFORE
            # ``done``, so the mark-committed happens while the client
            # is guaranteed to have seen the feedback frame.
            mark_feedback_committed(session_id, question_number)

            yield _sse_frame(
                "done",
                {"question_number": question_number, "answer_id": answer_id_str},
            )
            await logger.ainfo(
                "sse_feedback_done",
                question_number=question_number,
                empty_feedback=not parts,
            )

        except asyncio.CancelledError:
            # Story 3.4 v1.3.0 (BLOCKER #4 edge case): same reasoning as
            # the disconnect-mid-token branch — mark the feedback
            # committed so a reconnecting GET stream can advance.
            mark_feedback_committed(session_id, question_number)
            await logger.ainfo("sse_feedback_cancelled")
            raise
        except Exception as exc:
            await logger.aexception("sse_feedback_failed")
            # Story 3.4 v1.3.0 (BLOCKER #4 edge case): the answer row is
            # committed but the feedback stream failed. Mark the flag
            # so the pause-loop can advance — the user will see an
            # error on the feedback message but Q_next still streams.
            mark_feedback_committed(session_id, question_number)
            yield _sse_frame(
                "error",
                {
                    "error": type(exc).__name__,
                    "message": str(exc),
                    "retryable": True,
                },
            )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
