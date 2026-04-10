"""Integration tests for the comprehension API router (Story 3.1).

The ``app_with_db`` fixture mirrors webhook/test_router.py but seeds an
``Installation`` + ``GitHubUser`` + session pair so the GET endpoint has
something to return.

GitHub-facing helpers are patched at the *import site* used by the
handler and router (the Story 2.2 pattern) — never at the
``installation.service`` source module, since the imports are aliased.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.main import create_app
from helprs.modules.comprehension.infrastructure.models import SessionModel
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"

_TEST_GITHUB_USER_ID = 7777
_TEST_GITHUB_INSTALLATION_ID = 12345678


@pytest.fixture
async def app_with_db():
    """Create the app wired to a fresh test DB + seeded test data."""
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    application.state.session_factory = session_factory

    settings = get_settings()

    # Seed: installation + user + one (author, reviewer) session pair.
    async with session_factory() as bootstrap:
        installation = Installation(
            github_installation_id=_TEST_GITHUB_INSTALLATION_ID,
            account_login="acme",
            account_id=55555,
            account_type="Organization",
            repository_selection="all",
            app_slug="helprs",
            target_type="Organization",
            permissions={"pull_requests": "write", "issues": "write"},
            events=["pull_request"],
            suppression_labels=None,
        )
        bootstrap.add(installation)
        await bootstrap.flush()

        user = GitHubUser(
            github_id=_TEST_GITHUB_USER_ID,
            github_login="testuser",
            email="test@example.com",
            avatar_url=None,
            github_access_token_enc=fernet_encrypt("gho_test_token", settings.FERNET_KEY),
        )
        bootstrap.add(user)
        await bootstrap.flush()

        author = SessionModel(
            installation_id=installation.id,
            github_installation_id=_TEST_GITHUB_INSTALLATION_ID,
            repo_full_name="acme/repo",
            repo_owner="acme",
            repo_name="repo",
            pr_number=42,
            pr_title="Add foo",
            pr_head_sha="abc123",
            pr_diff_url="https://github.com/acme/repo/pull/42.diff",
            role="author",
            status="pending",
        )
        reviewer = SessionModel(
            installation_id=installation.id,
            github_installation_id=_TEST_GITHUB_INSTALLATION_ID,
            repo_full_name="acme/repo",
            repo_owner="acme",
            repo_name="repo",
            pr_number=42,
            pr_title="Add foo",
            pr_head_sha="abc123",
            pr_diff_url="https://github.com/acme/repo/pull/42.diff",
            role="reviewer",
            status="pending",
        )
        bootstrap.add_all((author, reviewer))
        await bootstrap.commit()

        seeded = {
            "installation_id": installation.id,
            "user_id": user.id,
            "author_id": author.id,
            "reviewer_id": reviewer.id,
        }

    yield application, session_factory, seeded

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _patch_github_calls(monkeypatch):
    """Patch mint_installation_token + get_installations_for_user at the
    handler import site, and patch fetch_pr_diff at the router import
    site. Story 2.2 pattern: patching the *import* site is the only way
    ``from ... import foo`` references get replaced.
    """
    mint = AsyncMock(return_value="ghs_test_token")
    access_list = AsyncMock(return_value=[])  # each test overrides
    diff = AsyncMock(return_value="diff --git a/foo b/foo\n+new line\n")

    monkeypatch.setattr(
        "helprs.modules.comprehension.application.handlers.mint_installation_token",
        mint,
    )
    monkeypatch.setattr(
        "helprs.modules.comprehension.application.handlers.get_installations_for_user",
        access_list,
    )
    monkeypatch.setattr(
        "helprs.modules.comprehension.presentation.routers.fetch_pr_diff",
        diff,
    )
    return mint, access_list, diff


@pytest.fixture
async def app_client(app_with_db):
    application, _, _ = app_with_db
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
        yield ac


def _bearer(user_id) -> dict:
    get_settings.cache_clear()
    settings = get_settings()
    token = create_access_token(
        {"sub": str(user_id), "github_login": "testuser"},
        settings.SECRET_KEY,
    )
    return {"Authorization": f"Bearer {token}"}


class TestHappyPath:
    async def test_returns_session_response_with_mocked_diff(self, app_client, app_with_db, _patch_github_calls):
        _, session_factory, seeded = app_with_db
        _, access_list, diff = _patch_github_calls

        # Load the seeded Installation into the access-check mock's return value.
        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        resp = await app_client.get(
            f"/api/v1/sessions/{seeded['author_id']}",
            headers=_bearer(seeded["user_id"]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["id"] == str(seeded["author_id"])
        assert body["repo_full_name"] == "acme/repo"
        assert body["repo_owner"] == "acme"
        assert body["repo_name"] == "repo"
        assert body["pr_number"] == 42
        assert body["pr_title"] == "Add foo"
        assert body["role"] == "author"
        assert body["status"] == "pending"
        assert body["question_count"] == 0
        assert body["diff"].startswith("diff --git")
        assert "created_at" in body and "updated_at" in body

        diff.assert_awaited_once()


class TestAccessControl:
    async def test_returns_403_when_user_has_no_installation_access(self, app_client, app_with_db, _patch_github_calls):
        _, _, seeded = app_with_db
        _, access_list, _ = _patch_github_calls
        access_list.return_value = []  # no accessible installations

        resp = await app_client.get(
            f"/api/v1/sessions/{seeded['author_id']}",
            headers=_bearer(seeded["user_id"]),
        )
        assert resp.status_code == 403

    async def test_returns_404_when_session_id_unknown(self, app_client, app_with_db, _patch_github_calls):
        _, _, seeded = app_with_db
        resp = await app_client.get(
            f"/api/v1/sessions/{uuid.uuid4()}",
            headers=_bearer(seeded["user_id"]),
        )
        assert resp.status_code == 404

    async def test_returns_401_when_missing_bearer_token(self, app_client, app_with_db):
        _, _, seeded = app_with_db
        resp = await app_client.get(f"/api/v1/sessions/{seeded['author_id']}")
        assert resp.status_code == 401


class TestNoPersistenceInvariant:
    async def test_diff_fetch_does_not_write_to_sessions_table(self, app_client, app_with_db, _patch_github_calls):
        """NFR13: a GET must not mutate any DB state."""
        _, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
            before_count = (await s.execute(select(func.count()).select_from(SessionModel))).scalar_one()
            before_row = (
                await s.execute(select(SessionModel).where(SessionModel.id == seeded["author_id"]))
            ).scalar_one()
            before_updated_at = before_row.updated_at
            before_pr_head = before_row.pr_head_sha
        access_list.return_value = [inst]

        resp = await app_client.get(
            f"/api/v1/sessions/{seeded['author_id']}",
            headers=_bearer(seeded["user_id"]),
        )
        assert resp.status_code == 200

        async with session_factory() as s:
            after_count = (await s.execute(select(func.count()).select_from(SessionModel))).scalar_one()
            after_row = (
                await s.execute(select(SessionModel).where(SessionModel.id == seeded["author_id"]))
            ).scalar_one()

        assert after_count == before_count
        assert after_row.updated_at == before_updated_at
        assert after_row.pr_head_sha == before_pr_head


class TestDbPhaseBeforeHttpPhase:
    async def test_fetch_pr_diff_called_after_handler_returns(
        self, app_client, app_with_db, monkeypatch, _patch_github_calls
    ):
        """Structural proof: the handler finishes (access check, token mint)
        before ``fetch_pr_diff`` fires. Captures call order via a shared
        list both mocks append to.
        """
        _, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        calls: list[str] = []

        from helprs.modules.comprehension.application import handlers as handlers_mod
        from helprs.modules.comprehension.presentation import routers as routers_mod

        original_handle = handlers_mod.GetSessionHandler.handle

        async def recording_handle(self, query):
            calls.append("handler_start")
            result = await original_handle(self, query)
            calls.append("handler_end")
            return result

        async def recording_fetch(**kwargs):
            calls.append("fetch_pr_diff")
            return "diff --git a/f b/f\n"

        monkeypatch.setattr(handlers_mod.GetSessionHandler, "handle", recording_handle)
        monkeypatch.setattr(routers_mod, "fetch_pr_diff", recording_fetch)

        resp = await app_client.get(
            f"/api/v1/sessions/{seeded['author_id']}",
            headers=_bearer(seeded["user_id"]),
        )
        assert resp.status_code == 200, resp.text

        # handler_end must strictly precede the diff fetch.
        assert calls == ["handler_start", "handler_end", "fetch_pr_diff"], calls
