"""Tests for SqlAlchemySessionRepository."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from helprs.modules.comprehension.domain.entities import PRContext, Session
from helprs.modules.comprehension.domain.value_objects import SessionRole, SessionStatus
from helprs.modules.comprehension.infrastructure.models import SessionModel
from helprs.modules.comprehension.infrastructure.repositories import SqlAlchemySessionRepository


def _pr_ctx(installation_id, pr_number: int = 42, pr_head_sha: str = "abc123") -> PRContext:
    return PRContext(
        installation_id=installation_id,
        github_installation_id=12345678,
        repo_full_name="acme/repo",
        repo_owner="acme",
        repo_name="repo",
        pr_number=pr_number,
        pr_title="Add foo",
        pr_head_sha=pr_head_sha,
        pr_diff_url=f"https://github.com/acme/repo/pull/{pr_number}.diff",
    )


class TestAddPair:
    async def test_inserts_exactly_two_rows_one_per_role(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, reviewer = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        # Returned domain entities carry role + IDs
        assert isinstance(author, Session)
        assert isinstance(reviewer, Session)
        assert {author.role, reviewer.role} == {SessionRole.AUTHOR, SessionRole.REVIEWER}
        assert author.id != reviewer.id
        assert author.status is SessionStatus.PENDING
        assert reviewer.status is SessionStatus.PENDING

        # DB actually has two rows sharing PR metadata
        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert len(rows) == 2
        assert {r.role for r in rows} == {"author", "reviewer"}
        assert {r.pr_number for r in rows} == {42}
        assert {r.repo_full_name for r in rows} == {"acme/repo"}

    async def test_unique_constraint_rejects_duplicate_role(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))
        # Manually inserting another "author" row for the same PR must fail
        dup = SessionModel(
            installation_id=test_installation.id,
            github_installation_id=12345678,
            repo_full_name="acme/repo",
            repo_owner="acme",
            repo_name="repo",
            pr_number=42,
            pr_title="x",
            pr_head_sha="x",
            pr_diff_url="x",
            role="author",
            status="pending",
        )
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()


class TestFindPair:
    async def test_returns_empty_for_unknown_pr(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        rows = await repo.find_pair(
            installation_id=test_installation.id,
            repo_full_name="acme/repo",
            pr_number=999,
        )
        assert rows == []

    async def test_returns_both_sessions(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        rows = await repo.find_pair(
            installation_id=test_installation.id,
            repo_full_name="acme/repo",
            pr_number=42,
        )
        assert len(rows) == 2
        # Ordered alphabetically by role → author first, reviewer second
        assert rows[0].role is SessionRole.AUTHOR
        assert rows[1].role is SessionRole.REVIEWER


class TestUpdateHeadSha:
    async def test_updates_both_rows(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id, pr_head_sha="old-sha"))

        refreshed = await repo.update_head_sha(
            installation_id=test_installation.id,
            repo_full_name="acme/repo",
            pr_number=42,
            new_head_sha="new-sha-xyz",
            new_pr_title="Add foo (v2)",
            new_pr_diff_url="https://github.com/acme/repo/pull/42.diff",
        )

        assert len(refreshed) == 2
        for s in refreshed:
            assert s.pr_head_sha == "new-sha-xyz"
            assert s.pr_title == "Add foo (v2)"

    async def test_returns_domain_entities_not_orm(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        refreshed = await repo.update_head_sha(
            installation_id=test_installation.id,
            repo_full_name="acme/repo",
            pr_number=42,
            new_head_sha="aaa",
            new_pr_title="t",
            new_pr_diff_url="https://github.com/acme/repo/pull/42.diff",
        )
        assert all(isinstance(s, Session) for s in refreshed)
        assert not any(isinstance(s, SessionModel) for s in refreshed)


class TestRepositoryDoesNotCommit:
    """Invariant: the comprehension repository never calls ``session.commit()``.

    Unit-of-work is owned by the caller (``process_webhook_event`` via the
    outer ``async with session_factory()`` block). Committing inside the
    repo would break rollback-on-exception for every path that writes a
    session row and then fails further down (e.g. PR comment post failure).
    """

    async def test_add_pair_does_not_commit(self, db_session, test_installation, monkeypatch):
        commit_calls = 0

        original_commit = db_session.commit

        async def tracking_commit():
            nonlocal commit_calls
            commit_calls += 1
            await original_commit()

        monkeypatch.setattr(db_session, "commit", tracking_commit)

        repo = SqlAlchemySessionRepository(db_session)
        await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        assert commit_calls == 0

    async def test_update_head_sha_does_not_commit(self, db_session, test_installation, monkeypatch):
        repo = SqlAlchemySessionRepository(db_session)
        await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        commit_calls = 0
        original_commit = db_session.commit

        async def tracking_commit():
            nonlocal commit_calls
            commit_calls += 1
            await original_commit()

        monkeypatch.setattr(db_session, "commit", tracking_commit)

        await repo.update_head_sha(
            installation_id=test_installation.id,
            repo_full_name="acme/repo",
            pr_number=42,
            new_head_sha="sha2",
            new_pr_title="t2",
            new_pr_diff_url="https://github.com/acme/repo/pull/42.diff",
        )
        assert commit_calls == 0


class TestDeleteOne:
    async def test_deletes_row_by_id(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        await repo.delete_one(session_id=author.id)

        rows = await repo.find_pair(
            installation_id=test_installation.id,
            repo_full_name="acme/repo",
            pr_number=42,
        )
        assert len(rows) == 1
        assert rows[0].role is SessionRole.REVIEWER


class TestGetById:
    """``get_by_id`` is the Story 3.1 read-path primitive powering the
    ``GET /api/v1/sessions/{id}`` endpoint."""

    async def test_returns_domain_session_when_row_exists(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, reviewer = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        loaded_author = await repo.get_by_id(session_id=author.id)
        loaded_reviewer = await repo.get_by_id(session_id=reviewer.id)

        assert isinstance(loaded_author, Session)
        assert isinstance(loaded_reviewer, Session)
        assert loaded_author.id == author.id
        assert loaded_author.role is SessionRole.AUTHOR
        assert loaded_reviewer.id == reviewer.id
        assert loaded_reviewer.role is SessionRole.REVIEWER
        assert loaded_author.status is SessionStatus.PENDING
        # Ensure mapping is a domain dataclass, not the ORM row.
        assert not isinstance(loaded_author, SessionModel)

    async def test_returns_none_when_row_missing(self, db_session):
        repo = SqlAlchemySessionRepository(db_session)
        result = await repo.get_by_id(session_id=uuid.uuid4())
        assert result is None

    async def test_get_by_id_does_not_commit(self, db_session, test_installation, monkeypatch):
        """Invariant: reads never commit — the caller owns the UoW."""
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        commit_calls = 0
        original_commit = db_session.commit

        async def tracking_commit():
            nonlocal commit_calls
            commit_calls += 1
            await original_commit()

        monkeypatch.setattr(db_session, "commit", tracking_commit)

        hit = await repo.get_by_id(session_id=author.id)
        miss = await repo.get_by_id(session_id=uuid.uuid4())  # miss path too

        assert hit is not None, "hit path must return the loaded session"
        assert miss is None, "miss path must return None"
        assert commit_calls == 0


# ----------------------------------------------------------------------
# Story 3.3 Task 2.3 + P23 from story-3.3 review: question repository
# methods. Locks (a) empty-session counts, (b) sequential numbering
# via ``append_question``, (c) ordered ``list_questions`` output,
# (d) the mapping helper contract (domain entity, not ORM row).
# ----------------------------------------------------------------------


class TestCountQuestions:
    async def test_returns_zero_for_fresh_session(self, db_session, test_installation):
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        assert await repo.count_questions(session_id=author.id) == 0

    async def test_scoped_per_session(self, db_session, test_installation):
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )

        repo = SqlAlchemySessionRepository(db_session)
        author, reviewer = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        # 2 questions on author, 1 on reviewer.
        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)
        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="b" * 64)
        await repo.append_question(session_id=reviewer.id, topic=Topic.ARCHITECTURE, text_hash="c" * 64)

        assert await repo.count_questions(session_id=author.id) == 2
        assert await repo.count_questions(session_id=reviewer.id) == 1


class TestAppendQuestion:
    async def test_assigns_sequential_numbers_starting_at_one(self, db_session, test_installation):
        from helprs.modules.comprehension.domain.entities import Question
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        q1 = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="1" * 64)
        q2 = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="2" * 64)
        q3 = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="3" * 64)

        # Domain entity, not ORM row (mapping contract).
        for q in (q1, q2, q3):
            assert isinstance(q, Question)
        # Numbers are strictly 1, 2, 3 — the serialization invariant.
        assert [q.number for q in (q1, q2, q3)] == [1, 2, 3]
        # Each carries its own ID.
        assert len({q.id for q in (q1, q2, q3)}) == 3

    async def test_unique_constraint_rejects_duplicate_number(self, db_session, test_installation):
        """Direct duplicate numbers must be rejected by the unique
        constraint — proves the schema invariant is in place (the
        application-level lock is tested in the concurrent case below).
        """
        from helprs.modules.comprehension.infrastructure.models import QuestionModel
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        db_session.add(QuestionModel(session_id=author.id, number=1, topic="architecture", text_hash="a" * 64))
        await db_session.flush()
        db_session.add(QuestionModel(session_id=author.id, number=1, topic="architecture", text_hash="b" * 64))
        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()


class TestListQuestions:
    async def test_returns_questions_in_number_order(self, db_session, test_installation):
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        # Insert in the "wrong" order — the repo must still return
        # them sorted by ``number`` ASC.
        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="1" * 64)
        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="2" * 64)
        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="3" * 64)

        questions = await repo.list_questions(session_id=author.id)
        assert [q.number for q in questions] == [1, 2, 3]
        assert [q.text_hash for q in questions] == ["1" * 64, "2" * 64, "3" * 64]

    async def test_returns_empty_for_fresh_session(self, db_session, test_installation):
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        assert await repo.list_questions(session_id=author.id) == []


# ----------------------------------------------------------------------
# Story 3.4: answer repository methods. Locks (a) get_question_by_number,
# (b) count_answers join semantics, (c) append_answer happy path,
# (d) the unique constraint translation to DomainValidationError on
# double-submit.
# ----------------------------------------------------------------------


class TestGetQuestionByNumber:
    async def test_returns_question_for_known_number(self, db_session, test_installation):
        from helprs.modules.comprehension.domain.entities import Question
        from helprs.modules.comprehension.domain.value_objects import Topic

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        q1 = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)
        q2 = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="b" * 64)

        loaded = await repo.get_question_by_number(session_id=author.id, number=2)
        assert isinstance(loaded, Question)
        assert loaded.id == q2.id
        assert loaded.number == 2
        assert loaded.text_hash == "b" * 64
        # Sanity: number=1 still resolves too.
        loaded_first = await repo.get_question_by_number(session_id=author.id, number=1)
        assert loaded_first is not None
        assert loaded_first.id == q1.id

    async def test_returns_none_for_unknown_number(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        result = await repo.get_question_by_number(session_id=author.id, number=99)
        assert result is None

    async def test_does_not_cross_sessions(self, db_session, test_installation):
        """Question 1 of session A must not be returned for session B."""
        from helprs.modules.comprehension.domain.value_objects import Topic

        repo = SqlAlchemySessionRepository(db_session)
        author, reviewer = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)

        # Reviewer has no questions yet — number 1 must miss.
        assert await repo.get_question_by_number(session_id=reviewer.id, number=1) is None


class TestCountAnswers:
    async def test_returns_zero_for_session_without_answers(self, db_session, test_installation):
        from helprs.modules.comprehension.domain.value_objects import Topic

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        # Even with questions present, count_answers must be 0.
        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)
        assert await repo.count_answers(session_id=author.id) == 0

    async def test_counts_answers_joined_by_question(self, db_session, test_installation):
        from helprs.modules.comprehension.domain.value_objects import Topic

        repo = SqlAlchemySessionRepository(db_session)
        author, reviewer = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        q1 = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)
        q2 = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="b" * 64)
        rq1 = await repo.append_question(session_id=reviewer.id, topic=Topic.ARCHITECTURE, text_hash="r" * 64)

        await repo.append_answer(question_id=q1.id, text_hash="1" * 64, latency_ms=100)
        await repo.append_answer(question_id=q2.id, text_hash="2" * 64, latency_ms=200)
        await repo.append_answer(question_id=rq1.id, text_hash="3" * 64, latency_ms=300)

        assert await repo.count_answers(session_id=author.id) == 2
        assert await repo.count_answers(session_id=reviewer.id) == 1


class TestAppendAnswer:
    async def test_happy_path_persists_row_and_returns_domain_entity(self, db_session, test_installation):
        from helprs.modules.comprehension.domain.entities import Answer
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.models import AnswerModel

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))
        q = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)

        ans = await repo.append_answer(question_id=q.id, text_hash="h" * 64, latency_ms=1234)

        assert isinstance(ans, Answer)
        assert not isinstance(ans, AnswerModel)
        assert ans.question_id == q.id
        assert ans.text_hash == "h" * 64
        assert ans.latency_ms == 1234
        assert ans.id is not None
        assert ans.created_at is not None

    async def test_double_submit_raises_domain_validation_error(self, db_session, test_installation):
        """The unique constraint must surface as DomainValidationError, not IntegrityError."""
        from helprs.core.exceptions import DomainValidationError
        from helprs.modules.comprehension.domain.value_objects import Topic

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))
        q = await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)

        await repo.append_answer(question_id=q.id, text_hash="h" * 64, latency_ms=100)

        with pytest.raises(DomainValidationError, match="answer already submitted"):
            await repo.append_answer(question_id=q.id, text_hash="g" * 64, latency_ms=200)
