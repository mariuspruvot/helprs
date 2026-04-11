"""Tests for ``presentation/answer_pubsub.py``.

Story 3.4: locks down the in-process question-text registry that
bridges the GET stream and the POST answer endpoint. Story 3.4 D1
(code-review decision) removed the answer-signal mechanism — the
GET stream now polls ``count_answers`` against the DB, so the only
surface left is the question-text bucket.
"""

import uuid

import pytest

from helprs.modules.comprehension.presentation.answer_pubsub import (
    clear_session,
    get_question_text,
    is_feedback_committed,
    mark_feedback_committed,
    reset_answer_pubsub,
    stash_question_text,
)


class TestStashAndGet:
    def test_stash_then_get_round_trips(self):
        session_id = uuid.uuid4()
        question_id = uuid.uuid4()

        stash_question_text(session_id, question_id, "What did you assume?")
        assert get_question_text(session_id, question_id) == "What did you assume?"

    def test_unknown_session_returns_none(self):
        assert get_question_text(uuid.uuid4(), uuid.uuid4()) is None

    def test_unknown_question_in_known_session_returns_none(self):
        session_id = uuid.uuid4()
        stash_question_text(session_id, uuid.uuid4(), "first")
        assert get_question_text(session_id, uuid.uuid4()) is None

    def test_cross_session_isolation(self):
        """Stashing in session A must not bleed into session B."""
        session_a = uuid.uuid4()
        session_b = uuid.uuid4()
        question_id = uuid.uuid4()

        stash_question_text(session_a, question_id, "A text")
        # Same question_id, different session — must stay None.
        assert get_question_text(session_b, question_id) is None

    def test_multiple_questions_per_session(self):
        session_id = uuid.uuid4()
        q1, q2 = uuid.uuid4(), uuid.uuid4()
        stash_question_text(session_id, q1, "first")
        stash_question_text(session_id, q2, "second")

        assert get_question_text(session_id, q1) == "first"
        assert get_question_text(session_id, q2) == "second"


class TestClearSession:
    def test_clear_drops_text(self):
        session_id = uuid.uuid4()
        q_id = uuid.uuid4()
        stash_question_text(session_id, q_id, "x")

        clear_session(session_id)

        assert get_question_text(session_id, q_id) is None

    def test_clear_unknown_session_is_noop(self):
        # Should not raise.
        clear_session(uuid.uuid4())

    def test_clear_drops_feedback_committed_flags(self):
        """Story 3.4 v1.3.0 BLOCKER #4: ``clear_session`` must wipe
        both the question-text registry AND the feedback-committed
        flag set so a long-running worker doesn't leak either.
        """
        session_id = uuid.uuid4()
        mark_feedback_committed(session_id, 1)
        mark_feedback_committed(session_id, 2)
        assert is_feedback_committed(session_id, 1) is True
        assert is_feedback_committed(session_id, 2) is True

        clear_session(session_id)

        assert is_feedback_committed(session_id, 1) is False
        assert is_feedback_committed(session_id, 2) is False


class TestResetAnswerPubsub:
    def test_reset_wipes_everything(self):
        for _ in range(3):
            sid = uuid.uuid4()
            stash_question_text(sid, uuid.uuid4(), "x")

        reset_answer_pubsub()

        assert get_question_text(uuid.uuid4(), uuid.uuid4()) is None

    def test_reset_wipes_feedback_committed_flags(self):
        """Story 3.4 v1.3.0 BLOCKER #4: the test-only reset helper
        must wipe the feedback-committed registry so cross-test bleed
        cannot cause a later test to see a stale "already committed"
        state.
        """
        sid = uuid.uuid4()
        mark_feedback_committed(sid, 1)
        assert is_feedback_committed(sid, 1) is True

        reset_answer_pubsub()

        assert is_feedback_committed(sid, 1) is False


class TestFeedbackCommitted:
    """Story 3.4 v1.3.0 BLOCKER #4: feedback-committed signal."""

    def test_mark_then_check_is_true(self):
        sid = uuid.uuid4()
        mark_feedback_committed(sid, 1)
        assert is_feedback_committed(sid, 1) is True

    def test_unmarked_is_false(self):
        assert is_feedback_committed(uuid.uuid4(), 1) is False

    def test_other_question_number_is_false(self):
        """Marking question 1 must not leak into question 2."""
        sid = uuid.uuid4()
        mark_feedback_committed(sid, 1)
        assert is_feedback_committed(sid, 2) is False

    def test_cross_session_isolation(self):
        sid_a = uuid.uuid4()
        sid_b = uuid.uuid4()
        mark_feedback_committed(sid_a, 1)
        assert is_feedback_committed(sid_b, 1) is False

    def test_mark_is_idempotent(self):
        """Calling mark twice is a no-op; the set semantics dedupe."""
        sid = uuid.uuid4()
        mark_feedback_committed(sid, 1)
        mark_feedback_committed(sid, 1)
        assert is_feedback_committed(sid, 1) is True

    def test_multiple_questions_in_same_session(self):
        sid = uuid.uuid4()
        mark_feedback_committed(sid, 1)
        mark_feedback_committed(sid, 2)
        mark_feedback_committed(sid, 3)
        assert is_feedback_committed(sid, 1) is True
        assert is_feedback_committed(sid, 2) is True
        assert is_feedback_committed(sid, 3) is True
        assert is_feedback_committed(sid, 4) is False


@pytest.fixture(autouse=True)
def _wipe_between_tests():
    """Defensive: even with the conftest autouse fixture, this file's
    direct registry interactions deserve their own teardown so a single
    test failure cannot cascade into adjacent ones.
    """
    reset_answer_pubsub()
    yield
    reset_answer_pubsub()
