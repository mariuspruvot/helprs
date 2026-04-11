"""Server-Sent Events streaming for comprehension sessions.

Story 3.3: ``GET /api/v1/sessions/{session_id}/stream`` streams
Socratic questions one token at a time so the UI can show the first
token within 1 s (NFR3) and the first complete question within 3 s
(NFR2) of the request being accepted.

Architecture rules (non-negotiable — enforced by the tests in
``test_sse_stream.py``):

* **DB phase / HTTP phase split.** The request-scoped ``AsyncSession``
  from ``get_db`` is ONLY used for the initial load + auth check +
  BYOK decryption + token mint. Once the stream generator starts,
  the endpoint has exited the ``get_db`` block semantically (FastAPI
  still holds it until the ``StreamingResponse`` finishes, but NO
  code inside the generator touches ``db``). Per-question writes use
  ``get_db_context`` — a fresh short-lived session per commit.
* **Zero-retention BYOK.** The decrypted API key flows as an argument
  into ``PydanticAILLMProvider.stream_question`` and is discarded
  when the function returns. It is never stashed on the provider
  instance, a module global, or the generator's captured frame
  longer than necessary.
* **Hash-only persistence.** The accumulated question text is
  SHA-256-hashed before it reaches ``append_question``. No column
  exists for the verbatim text; adding one is FORBIDDEN (FR35/NFR14).
* **Manual framing.** We write ``event: / data: / \\n\\n`` bytes
  directly to the ``StreamingResponse`` rather than adding
  ``sse-starlette`` as a new dep — the framing is 20 lines and the
  dep is not worth it.
"""

import asyncio
import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from helprs.core.database import get_db_context
from helprs.core.dependencies import DbSession, GetSettings, get_current_user
from helprs.core.exceptions import DomainValidationError
from helprs.core.middleware import limiter
from helprs.modules.comprehension.application.handlers import GetSessionHandler
from helprs.modules.comprehension.application.queries import GetSessionQuery
from helprs.modules.comprehension.domain.value_objects import Topic
from helprs.modules.comprehension.infrastructure.agents import PydanticAILLMProvider
from helprs.modules.comprehension.infrastructure.diff_refs import extract_file_refs
from helprs.modules.comprehension.infrastructure.github_diff import fetch_pr_diff
from helprs.modules.comprehension.infrastructure.repositories import SqlAlchemySessionRepository
from helprs.modules.comprehension.presentation.dependencies import get_llm_provider
from helprs.modules.installation.service import decrypt_byok_key, get_byok_config

logger = structlog.get_logger()

sse_router = APIRouter(prefix="/sessions", tags=["sessions-sse"])


def _sse_frame(event: str, data: dict[str, Any]) -> bytes:
    """Encode a single SSE frame: ``event:`` + ``data:`` + blank line.

    Pure function — unit-tested separately from the endpoint so the
    framing contract is locked down independently of DB/HTTP wiring.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


@sse_router.get("/{session_id}/stream")
@limiter.limit("20/minute")
async def stream_session(
    session_id: UUID,
    request: Request,
    db: DbSession,
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

    Errors before any SSE frame (404, 403, missing BYOK → 422) are
    returned as normal JSON responses — the client's ``EventSource``
    sees them as a failed handshake and can render an error banner.
    """
    # ==================================================================
    # DB phase: load session, authorize, mint token, decrypt BYOK,
    # snapshot already-persisted question hashes. After this block,
    # ``db`` is NOT touched again by any code in the stream generator.
    # ==================================================================
    handler = GetSessionHandler(db, settings)
    result = await handler.handle(GetSessionQuery(session_id=session_id, requesting_user=user))
    session = result.session
    installation_token = result.installation_token
    total = session.total_questions or 5

    byok = await get_byok_config(db, session.installation_id)
    if byok is None:
        # Raise BEFORE entering the generator so the client sees a
        # standard JSON error response, not a half-open SSE stream.
        raise DomainValidationError(f"Installation {session.installation_id} has no BYOK key configured")
    api_key = decrypt_byok_key(byok, settings.FERNET_KEY)

    # Count + list existing questions so the stream only generates the
    # missing tail. ``list_questions`` gives us hashes (for logging) +
    # numbers; we need the count to resume the loop at ``last + 1``.
    existing = await SqlAlchemySessionRepository(db).list_questions(session_id=session_id)
    already_generated = len(existing)

    # Snapshot session metadata into plain locals so the generator
    # does not lazy-load ORM attributes after the DB scope is gone.
    repo_owner = session.repo_owner
    repo_name = session.repo_name
    pr_number = session.pr_number
    session_role = session.role
    session_id_str = str(session_id)

    # ==================================================================
    # HTTP / STREAM phase
    # ==================================================================
    async def generator() -> AsyncIterator[bytes]:
        # Bind session id on the stream's task scope so every log line
        # inside the generator is joinable.
        structlog.contextvars.bind_contextvars(session_id=session_id_str)
        try:
            # Diff fetch — in-memory, never persisted (NFR13).
            diff = await fetch_pr_diff(
                owner=repo_owner,
                repo=repo_name,
                pr_number=pr_number,
                installation_token=installation_token,
            )

            # Story 3.3 passes an empty ``previous_questions`` list to
            # the LLM because we only have hashes, not text. The LLM
            # gets a "don't repeat" instruction but no history.
            # Story 3.5 will feed back the full text list by keeping
            # it in memory for the duration of the stream.
            previous_texts: list[str] = []

            client_gone = False
            for _loop_number in range(already_generated + 1, total + 1):
                # Give up early if the client went away (back button,
                # tab close). Checked every loop iteration so we
                # stop minting LLM tokens the user cannot see.
                if await request.is_disconnected():
                    await logger.ainfo("sse_stream_client_disconnected", number=_loop_number)
                    return

                question_id = str(uuid.uuid4())
                parts: list[str] = []
                async for token in llm.stream_question(
                    pr_diff=diff,
                    role=session_role,
                    previous_questions=previous_texts,
                    api_key=api_key,
                ):
                    # P10: check disconnect inside the token loop so we
                    # stop streaming LLM tokens immediately when the
                    # client goes away, not just between questions.
                    # This matters because a single question can burn
                    # thousands of BYOK-billed tokens.
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
                    # Do NOT persist a half-streamed question. The
                    # next reconnection (if any) will start fresh from
                    # ``already_generated`` which the DB still reports.
                    return

                # P11: reject empty LLM output rather than persisting a
                # row with ``sha256("")``. An empty question is never a
                # legitimate outcome — surface it as an error frame.
                if not parts:
                    raise RuntimeError("LLM yielded no tokens for question")

                text = "".join(parts)
                text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                file_refs = extract_file_refs(diff, text)

                # Fresh short-lived session per commit — the
                # request-scoped ``db`` is intentionally NOT reused.
                async with get_db_context() as tx:
                    # P8: use the DB-assigned number from append_question
                    # rather than the Python loop variable. Under concurrent
                    # streams the assigned number may diverge from the loop
                    # variable (see two-tab scenario in review findings D1).
                    persisted = await SqlAlchemySessionRepository(tx).append_question(
                        session_id=session_id,
                        topic=Topic.ARCHITECTURE,  # TODO(story-3.5): topic selection
                        text_hash=text_hash,
                    )

                previous_texts.append(text)

                yield _sse_frame(
                    "question",
                    {
                        "question_id": question_id,
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

            # P9: report the actual persisted count rather than the
            # target ``total``. Opens a fresh short-lived session so
            # we don't reach back into ``db`` after the DB phase.
            async with get_db_context() as tx:
                actual_count = await SqlAlchemySessionRepository(tx).count_questions(
                    session_id=session_id,
                )

            yield _sse_frame(
                "done",
                {"session_id": session_id_str, "question_count": actual_count},
            )
            await logger.ainfo("sse_stream_done", question_count=actual_count, total=total)

        except asyncio.CancelledError:
            # Client disconnect surfaced via task cancellation — log
            # and re-raise so the server-side cleanup runs cleanly.
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
            # Tell nginx / proxies NOT to buffer our stream — required
            # for token-by-token delivery to survive a proxy.
            "X-Accel-Buffering": "no",
        },
    )
