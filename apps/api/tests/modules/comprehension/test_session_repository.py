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
