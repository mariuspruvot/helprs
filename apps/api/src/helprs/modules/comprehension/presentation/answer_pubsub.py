"""In-process question-text + feedback-committed registry.

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

Story 3.4 v1.3.0 (manual QA BLOCKER #4, 2026-04-11): the POST endpoint
commits the ``AnswerModel`` row BEFORE starting the feedback stream
(Story 3.4 P2 code-review patch — so a mid-stream disconnect does not
lose the user's answer). But that means ``count_answers`` increments
as soon as the POST hits its ``async with get_db_context()`` exit,
several seconds BEFORE the feedback stream completes. The GET stream's
pause-loop unblocks on the increment and starts emitting Q_next tokens
while the POST is still streaming F_current. Visual rendering order
becomes ``Q / A / Q_next / F`` instead of ``Q / A / F / Q_next``.

Fix: an explicit feedback-committed signal keyed by
``(session_id, question_number)``. The POST calls
``mark_feedback_committed(...)`` AFTER yielding the ``feedback`` frame;
the GET pause-loop additionally polls ``is_feedback_committed(...)``
before advancing past iteration N. ``count_answers`` alone is no longer
sufficient. The flag lives in process memory alongside the question
texts; ``clear_session`` wipes both. Single-replica assumption from the
module docstring carries over.

**Flag semantics — read this before changing call sites.** The flag
is morally a ``post_handler_done`` signal, not strictly "feedback
frame landed on the wire". ``submit_answer``'s generator fires
``mark_feedback_committed`` on FOUR exit paths:

1. Happy path: after yielding the authoritative ``feedback`` frame,
   before yielding ``done``. This is the "frame really emitted" case.
2. Disconnect-mid-token: the client on the POST response disconnected
   while partial ``feedback_token`` frames were being yielded. No
   authoritative ``feedback`` frame ever landed.
3. ``asyncio.CancelledError``: the POST coroutine was cancelled; any
   yielded frames up to that point made it to the client, but the
   ``feedback`` frame may or may not have been reached.
4. Generic ``Exception``: the feedback stream raised (LLM 5xx, httpx
   reset, etc.); an ``error`` frame is yielded instead of ``feedback``.

Paths 2-4 are deliberate. Without them, an abandoned or failed POST
would leave any PARALLEL GET pause-loop (second tab, reconnecting
client) hanging on ``is_feedback_committed`` until
``_ANSWER_TIMEOUT_SECONDS`` — a ~30-minute frozen screen, which is a
worse failure mode than the rare two-tab wrong-ordering case where
tab-2's GET advances to Q_next after F_current failed on tab-1. The
gate is "let the pause-loop advance once the POST is no longer
blocking this question", not "the feedback frame was successfully
delivered". If you are tempted to rename this to ``mark_post_done``,
that is in fact the accurate semantics — the current name is kept
for continuity with the BLOCKER #4 kick-back report.

**Coordinate invariant.** ``question_number`` here is the 1-indexed
ordinal assigned when the GET stream calls ``append_question``
(question numbers are contiguous from 1..N). The pause-loop's
``target`` argument is the cumulative answer count the stream is
waiting to reach after question N is answered. These two values
coincide because:
(a) questions are numbered densely from 1, never renumbered;
(b) one answer per question (enforced by the unique constraint
    ``uq_answers_question_id`` on ``answers.question_id``);
(c) the in-order POST check rejects out-of-order submissions.
If a future feature ever introduces question renumbering, question
skipping, or a "redo question" flow, this flag must be re-keyed
(likely by ``question_id: UUID`` instead of ``question_number: int``)
or the pause-loop will observe false positives / deadlocks.

TODO(story-3.5): replace the in-process question-text + feedback-
committed registries with an out-of-process store (Postgres JSONB on
``sessions`` row, or Redis with TTL) so a POST landing on replica B can
resolve a question text stashed by a GET on replica A, and the pause-
loop on replica A can observe a feedback-committed signal set on
replica B.
"""

from uuid import UUID

# session_id -> {question_id -> verbatim text}
_question_texts: dict[UUID, dict[UUID, str]] = {}

# Story 4.1: ephemeral answer + feedback text for scoring.
# Same lifecycle as _question_texts — cleared by clear_session.
_answer_texts: dict[UUID, dict[UUID, str]] = {}
_feedback_texts: dict[UUID, dict[UUID, str]] = {}

# session_id -> set of question_numbers whose feedback stream has
# finished yielding the ``feedback`` frame. Used by the pause-loop to
# gate Q_next on "F_current is fully emitted", not just "answer row
# persisted" (BLOCKER #4, 2026-04-11).
_feedback_committed: dict[UUID, set[int]] = {}


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


def stash_answer_text(session_id: UUID, question_id: UUID, text: str) -> None:
    """Cache the verbatim answer text in process memory (Story 4.1).

    Called by ``submit_answer`` after the answer row is persisted.
    Used by the scoring phase to build the Q&A pairs for the LLM.
    """
    bucket = _answer_texts.setdefault(session_id, {})
    bucket[question_id] = text


def get_answer_text(session_id: UUID, question_id: UUID) -> str | None:
    """Resolve a previously-stashed answer text."""
    bucket = _answer_texts.get(session_id)
    if bucket is None:
        return None
    return bucket.get(question_id)


def stash_feedback_text(session_id: UUID, question_id: UUID, text: str) -> None:
    """Cache the verbatim feedback text in process memory (Story 4.1).

    Called by ``submit_answer`` after the feedback stream completes.
    Used by the scoring phase to build the Q&A pairs for the LLM.
    """
    bucket = _feedback_texts.setdefault(session_id, {})
    bucket[question_id] = text


def get_feedback_text(session_id: UUID, question_id: UUID) -> str | None:
    """Resolve a previously-stashed feedback text."""
    bucket = _feedback_texts.get(session_id)
    if bucket is None:
        return None
    return bucket.get(question_id)


def mark_feedback_committed(session_id: UUID, question_number: int) -> None:
    """Signal that the POST handler is DONE streaming for question
    ``question_number`` — regardless of whether the feedback frame
    actually landed on the wire.

    Fires from four call sites in ``submit_answer``'s generator:
    (1) happy path after ``yield _sse_frame("feedback", ...)``;
    (2) the client-disconnect-mid-``feedback_token`` early-return;
    (3) the ``except asyncio.CancelledError`` branch;
    (4) the ``except Exception`` branch (right before yielding
    ``error``).

    Until this fires, the GET stream's ``_wait_for_answer_count``
    pause-loop will NOT advance to ``question_number + 1``, preventing
    the Q/A/Q_next/F message-ordering race (BLOCKER #4). See the
    module docstring for why paths (2)-(4) are intentional and why
    the name is "committed" rather than "post_done".

    **Coordinate contract**: ``question_number`` is the 1-indexed
    question ordinal, which is equal (by construction) to the
    cumulative answer count after question N is answered. The
    pause-loop's ``target`` argument uses the same coordinate. If
    you change either coordinate, change BOTH. See module docstring
    for the full invariant.
    """
    bucket = _feedback_committed.setdefault(session_id, set())
    bucket.add(question_number)


def is_feedback_committed(session_id: UUID, question_number: int) -> bool:
    """Return True once ``mark_feedback_committed`` fired for this
    ``(session_id, question_number)``.

    Polled by ``_wait_for_answer_count`` in addition to
    ``count_answers``. The flag is morally "POST handler done" (see
    ``mark_feedback_committed`` for the four fire sites and
    ``answer_pubsub`` module docstring for semantics). ``question_number``
    MUST match the value ``submit_answer`` passes to
    ``mark_feedback_committed`` — i.e. the 1-indexed question ordinal,
    which equals the cumulative answer count after question N is
    answered (see module docstring "Coordinate invariant").
    """
    bucket = _feedback_committed.get(session_id)
    if bucket is None:
        return False
    return question_number in bucket


def clear_session(session_id: UUID) -> None:
    """Drop the registries for a finished session.

    Called by the GET stream's ``done`` path so a long-running uvicorn
    worker doesn't leak memory across the lifetime of every session
    that has ever streamed. Drops both the question-text cache and the
    feedback-committed flags.
    """
    _question_texts.pop(session_id, None)
    _answer_texts.pop(session_id, None)
    _feedback_texts.pop(session_id, None)
    _feedback_committed.pop(session_id, None)


def reset_answer_pubsub() -> None:
    """Test-only: wipe the registries to prevent cross-test bleed.

    Wired as a pytest autouse fixture in
    ``tests/modules/comprehension/conftest.py``.
    """
    _question_texts.clear()
    _answer_texts.clear()
    _feedback_texts.clear()
    _feedback_committed.clear()
