"""Tests for StartSessionHandler."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from helprs.core.exceptions import NotFoundError
from helprs.modules.comprehension.application.commands import StartSessionCommand
from helprs.modules.comprehension.application.handlers import StartSessionHandler
from helprs.modules.comprehension.domain.value_objects import SessionRole
from helprs.modules.comprehension.infrastructure.models import SessionModel


def _cmd(
    github_installation_id: int = 12345678,
    pr_labels: tuple[str, ...] | list[str] | None = None,
    pr_head_sha: str = "abc123",
    pr_title: str = "Add foo",
    pr_number: int = 42,
) -> StartSessionCommand:
    return StartSessionCommand(
        github_installation_id=github_installation_id,
        repo_full_name="acme/repo",
        repo_owner="acme",
        repo_name="repo",
        pr_number=pr_number,
        pr_title=pr_title,
        pr_head_sha=pr_head_sha,
        pr_diff_url=f"https://github.com/acme/repo/pull/{pr_number}.diff",
        pr_labels=tuple(pr_labels) if pr_labels else (),
    )


class TestHappyPath:
    async def test_creates_session_pair(self, db_session, test_installation):
        handler = StartSessionHandler(db_session)
        result = await handler.handle(_cmd())

        assert result.created is True
        assert result.suppressed is False
        assert result.comment_needed is True
        assert result.sessions is not None
        author, reviewer = result.sessions
        assert author.role is SessionRole.AUTHOR
        assert reviewer.role is SessionRole.REVIEWER

        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert len(rows) == 2


class TestSuppression:
    async def test_explicit_label_matches(self, db_session, test_installation):
        test_installation.suppression_labels = ["hotfix"]
        await db_session.flush()

        handler = StartSessionHandler(db_session)
        result = await handler.handle(_cmd(pr_labels=["hotfix"]))

        assert result.suppressed is True
        assert result.suppressed_by_label == "hotfix"
        assert result.created is False
        assert result.comment_needed is False
        assert result.sessions is None
        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert rows == []

    async def test_case_insensitive(self, db_session, test_installation):
        test_installation.suppression_labels = ["hotfix"]
        await db_session.flush()

        handler = StartSessionHandler(db_session)
        result = await handler.handle(_cmd(pr_labels=["HotFix"]))

        assert result.suppressed is True
        assert result.suppressed_by_label == "hotfix"

    async def test_default_labels_when_none(self, db_session, test_installation):
        # Installation has suppression_labels=None → falls back to defaults
        test_installation.suppression_labels = None
        await db_session.flush()

        handler = StartSessionHandler(db_session)
        result = await handler.handle(_cmd(pr_labels=["urgent"]))

        assert result.suppressed is True
        assert result.suppressed_by_label == "urgent"

    async def test_default_labels_when_empty_list(self, db_session, test_installation):
        # Empty list must fall back to defaults (``[] or defaults`` == defaults)
        test_installation.suppression_labels = []
        await db_session.flush()

        handler = StartSessionHandler(db_session)
        result = await handler.handle(_cmd(pr_labels=["trivial"]))

        assert result.suppressed is True
        assert result.suppressed_by_label == "trivial"

    async def test_no_suppression_when_labels_dont_match(self, db_session, test_installation):
        test_installation.suppression_labels = ["hotfix"]
        await db_session.flush()

        handler = StartSessionHandler(db_session)
        result = await handler.handle(_cmd(pr_labels=["feature"]))

        assert result.suppressed is False
        assert result.created is True
        assert result.comment_needed is True


class TestInstallationNotFound:
    async def test_raises_not_found(self, db_session):
        # No installation in DB at all
        handler = StartSessionHandler(db_session)
        with pytest.raises(NotFoundError):
            await handler.handle(_cmd(github_installation_id=99999999))

    async def test_raises_not_found_when_soft_deleted(self, db_session, test_installation):
        test_installation.deleted_at = datetime.now(UTC)
        await db_session.flush()

        handler = StartSessionHandler(db_session)
        with pytest.raises(NotFoundError):
            await handler.handle(_cmd())


class TestSynchronizePath:
    async def test_updates_existing_pair_without_recreating(self, db_session, test_installation):
        handler = StartSessionHandler(db_session)
        # First call creates the pair
        first = await handler.handle(_cmd(pr_head_sha="old-sha", pr_title="v1"))
        first_author_id = first.sessions[0].id  # type: ignore[index]

        # Second call: synchronize with new sha
        second = await handler.handle(_cmd(pr_head_sha="new-sha", pr_title="v2"))

        assert second.created is False
        assert second.comment_needed is False
        assert second.sessions is not None
        # Rows preserved, not deleted/re-inserted
        assert {s.id for s in second.sessions} == {first_author_id, first.sessions[1].id}  # type: ignore[index]

        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert len(rows) == 2
        assert all(r.pr_head_sha == "new-sha" for r in rows)
        assert all(r.pr_title == "v2" for r in rows)


class TestOrphanRecovery:
    async def test_single_row_recovered_to_pair(self, db_session, test_installation):
        # Seed a single orphan row directly
        orphan = SessionModel(
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
        db_session.add(orphan)
        await db_session.flush()

        handler = StartSessionHandler(db_session)
        result = await handler.handle(_cmd())

        assert result.created is True
        assert result.comment_needed is True
        # DB ends with exactly 2 rows, one per role
        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert len(rows) == 2
        assert {r.role for r in rows} == {"author", "reviewer"}
