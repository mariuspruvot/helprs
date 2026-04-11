"""In-process question-text registry.

Story 3.4: when the GET stream commits a question, it stashes the
verbatim text in this module's per-session dict so the POST handler
can resolve it back when the user submits an answer (the verbatim
text never touches disk — FR35/NFR14).

Story 3.4 D1 (code-review decision, 2026-04-11): the previous
``asyncio.Event``-based answer-signal mechanism was replaced with
``count_answers`` polling in ``sse.stream_session``. The DB is the
single source of truth — an in-memory event is just a cache that can
lie (lost-signal race when the POST signalled before the GET reached
``get_or_create_answer_signal`` + ``clear()``). Polling removes the
race entirely AND makes the endpoint multi-worker-safe for free
(obsoleting the Story 3.5 Redis pub/sub requirement for this path).

TODO(story-3.5): replace the in-process question-text registry with
an out-of-process store (Postgres JSONB on ``sessions`` row, or Redis
with TTL) so a POST landing on replica B can resolve a question text
stashed by a GET on replica A.
"""

from uuid import UUID

# session_id -> {question_id -> verbatim text}
_question_texts: dict[UUID, dict[UUID, str]] = {}


def stash_question_text(session_id: UUID, question_id: UUID, text: str) -> None:
    """Cache the verbatim question text in process memory.

    Called by ``stream_session`` after each successful question
    commit. The text never persists to disk; ``clear_session`` drops
    the entire per-session bucket once the stream completes.
    """
    bucket = _question_texts.setdefault(session_id, {})
    bucket[question_id] = text


def get_question_text(session_id: UUID, question_id: UUID) -> str | None:
    """Resolve a previously-stashed question text.

    Returns ``None`` if the registry was cleared (server restart, or
    the session has already finished). The POST handler maps that to
    a 422 with the documented ``question_text_unavailable_after_restart``
    error code.
    """
    bucket = _question_texts.get(session_id)
    if bucket is None:
        return None
    return bucket.get(question_id)


def clear_session(session_id: UUID) -> None:
    """Drop the registry for a finished session.

    Called by the GET stream's ``done`` path so a long-running uvicorn
    worker doesn't leak memory across the lifetime of every session
    that has ever streamed.
    """
    _question_texts.pop(session_id, None)


def reset_answer_pubsub() -> None:
    """Test-only: wipe the registry to prevent cross-test bleed.

    Wired as a pytest autouse fixture in
    ``tests/modules/comprehension/conftest.py``.
    """
    _question_texts.clear()
