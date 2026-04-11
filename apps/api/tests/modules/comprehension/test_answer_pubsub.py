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


class TestResetAnswerPubsub:
    def test_reset_wipes_everything(self):
        for _ in range(3):
            sid = uuid.uuid4()
            stash_question_text(sid, uuid.uuid4(), "x")

        reset_answer_pubsub()

        assert get_question_text(uuid.uuid4(), uuid.uuid4()) is None


@pytest.fixture(autouse=True)
def _wipe_between_tests():
    """Defensive: even with the conftest autouse fixture, this file's
    direct registry interactions deserve their own teardown so a single
    test failure cannot cascade into adjacent ones.
    """
    reset_answer_pubsub()
    yield
    reset_answer_pubsub()
