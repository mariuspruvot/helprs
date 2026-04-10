"""Tests for GetSessionHandler (Story 3.1).

The handler is the use-case seam for ``GET /api/v1/sessions/{id}``:
load → authorize → mint token. These tests patch
``get_installations_for_user`` and ``mint_installation_token`` at the
*handler's* import site (not the installation-service source site) so
the seam matches production wiring and Story 2.2's patching pattern
(see webhook/test_router.py::_patch_github_calls).
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from helprs.core.config import get_settings
from helprs.core.exceptions import ForbiddenError, NotFoundError
from helprs.modules.comprehension.application.handlers import GetSessionHandler
from helprs.modules.comprehension.application.queries import GetSessionQuery
from helprs.modules.comprehension.domain.entities import PRContext
from helprs.modules.comprehension.domain.value_objects import SessionRole, SessionStatus
from helprs.modules.comprehension.infrastructure.repositories import SqlAlchemySessionRepository
from helprs.modules.identity.models import GitHubUser


def _pr_ctx(installation_id) -> PRContext:
    return PRContext(
        installation_id=installation_id,
        github_installation_id=12345678,
        repo_full_name="acme/repo",
        repo_owner="acme",
        repo_name="repo",
        pr_number=42,
        pr_title="Add foo",
        pr_head_sha="abc123",
        pr_diff_url="https://github.com/acme/repo/pull/42.diff",
    )


async def _seed_user(db_session, github_id: int = 777) -> GitHubUser:
    user = GitHubUser(
        github_id=github_id,
        github_login=f"user-{github_id}",
        email=None,
        avatar_url=None,
        github_access_token_enc="enc-placeholder",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def patch_github(monkeypatch):
    """Patch GitHub-facing helpers at the handler's import site."""
    mint = AsyncMock(return_value="ghs_test_token")
    access_list = AsyncMock()
    monkeypatch.setattr(
        "helprs.modules.comprehension.application.handlers.mint_installation_token",
        mint,
    )
    monkeypatch.setattr(
        "helprs.modules.comprehension.application.handlers.get_installations_for_user",
        access_list,
    )
    return mint, access_list


class TestHappyPath:
    async def test_returns_result_with_session_token_and_zero_count(
        self, db_session, test_installation, settings, patch_github
    ):
        mint, access_list = patch_github
        access_list.return_value = [test_installation]

        repo = SqlAlchemySessionRepository(db_session)
        author, _reviewer = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))
        user = await _seed_user(db_session, github_id=777)

        handler = GetSessionHandler(db_session, settings)
        result = await handler.handle(GetSessionQuery(session_id=author.id, requesting_user=user))

        assert result.session.id == author.id
        assert result.session.role is SessionRole.AUTHOR
        assert result.session.status is SessionStatus.PENDING
        assert result.installation_token == "ghs_test_token"
        assert result.question_count == 0
        mint.assert_awaited_once_with(12345678, settings)
        access_list.assert_awaited_once()

    async def test_access_check_runs_exactly_once(self, db_session, test_installation, settings, patch_github):
        """Guard against N+1 on the FR26 check."""
        _, access_list = patch_github
        access_list.return_value = [test_installation]

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))
        user = await _seed_user(db_session, github_id=777)

        handler = GetSessionHandler(db_session, settings)
        await handler.handle(GetSessionQuery(session_id=author.id, requesting_user=user))

        assert access_list.await_count == 1

    async def test_handler_does_not_reselect_user(
        self, db_session, test_installation, settings, patch_github, monkeypatch
    ):
        """Regression guard: the handler must reuse the user passed in
        the query, never re-issue a ``SELECT GitHubUser WHERE ...``.
        """
        _, access_list = patch_github
        access_list.return_value = [test_installation]

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))
        user = await _seed_user(db_session, github_id=777)

        execute_calls: list[str] = []
        original_execute = db_session.execute

        async def spy_execute(statement, *args, **kwargs):
            compiled = str(statement)
            if "github_users" in compiled.lower() or "githubuser" in compiled.lower():
                execute_calls.append(compiled)
            return await original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db_session, "execute", spy_execute)

        handler = GetSessionHandler(db_session, settings)
        await handler.handle(GetSessionQuery(session_id=author.id, requesting_user=user))

        assert execute_calls == [], f"handler re-queried GitHubUser: {execute_calls}"


class TestErrorPaths:
    async def test_not_found_when_session_id_unknown(self, db_session, test_installation, settings, patch_github):
        _, access_list = patch_github
        access_list.return_value = [test_installation]
        user = await _seed_user(db_session, github_id=777)

        handler = GetSessionHandler(db_session, settings)

        with pytest.raises(NotFoundError):
            await handler.handle(GetSessionQuery(session_id=uuid.uuid4(), requesting_user=user))

    async def test_forbidden_when_user_has_no_matching_installation(
        self, db_session, test_installation, settings, patch_github
    ):
        _, access_list = patch_github
        access_list.return_value = []  # user has access to NO installations

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))
        user = await _seed_user(db_session, github_id=777)

        handler = GetSessionHandler(db_session, settings)

        with pytest.raises(ForbiddenError):
            await handler.handle(GetSessionQuery(session_id=author.id, requesting_user=user))

    async def test_forbidden_when_user_installations_do_not_include_sessions_one(
        self, db_session, test_installation, settings, patch_github
    ):
        """Return a different installation so the UUID comparison fails
        — proves the handler is checking IDs, not just truthiness.
        """
        from helprs.modules.installation.models import Installation

        _, access_list = patch_github
        other = Installation(
            github_installation_id=99999999,
            account_login="other",
            account_id=1,
            account_type="User",
            repository_selection="all",
            app_slug="helprs",
            target_type="User",
            permissions={},
            events=[],
            suppression_labels=None,
        )
        db_session.add(other)
        await db_session.flush()
        access_list.return_value = [other]

        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))
        user = await _seed_user(db_session, github_id=777)

        handler = GetSessionHandler(db_session, settings)

        with pytest.raises(ForbiddenError):
            await handler.handle(GetSessionQuery(session_id=author.id, requesting_user=user))
