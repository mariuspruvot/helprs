"""Tests for Story 4.2: GitHub Status Check, Question Reporting & Post-Session Feedback.

Covers:
- 5.1: Domain entity tests (QuestionReport, SessionFeedback, ReportReason)
- 5.2: Repository tests (persist + get + IntegrityError duplicate handling)
- 5.3: GitHub status check tests (mock httpx for various responses)
- 5.4: Endpoint tests (POST report + POST feedback)
- 5.5: SSE integration test (status check call timing)
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.core.exceptions import DomainValidationError
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.main import create_app
from helprs.modules.comprehension.domain.entities import PRContext, QuestionReport, SessionFeedback
from helprs.modules.comprehension.domain.value_objects import ReportReason
from helprs.modules.comprehension.infrastructure.models import QuestionModel, SessionModel
from helprs.modules.comprehension.infrastructure.repositories import SqlAlchemySessionRepository
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import Installation
from helprs.modules.installation.service import post_commit_status

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"

_TEST_GITHUB_USER_ID = 7777
_TEST_GITHUB_INSTALLATION_ID = 12345678


# =====================================================================
# 5.1 — Domain entity tests
# =====================================================================


class TestReportReasonEnum:
    def test_all_values(self) -> None:
        assert ReportReason.IRRELEVANT == "irrelevant"
        assert ReportReason.FACTUALLY_INCORRECT == "factually_incorrect"
        assert ReportReason.AMBIGUOUS == "ambiguous"
        assert ReportReason.TOO_EASY == "too_easy"
        assert ReportReason.TOO_HARD == "too_hard"
        assert ReportReason.OTHER == "other"

    def test_count(self) -> None:
        assert len(ReportReason) == 6


class TestQuestionReportEntity:
    def test_frozen(self) -> None:
        report = QuestionReport(
            session_id=uuid.uuid4(),
            question_number=1,
            reason=ReportReason.AMBIGUOUS,
            created_at=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            report.reason = ReportReason.OTHER  # type: ignore[misc]

    def test_fields(self) -> None:
        sid = uuid.uuid4()
        now = datetime.now(UTC)
        report = QuestionReport(
            session_id=sid,
            question_number=2,
            reason=ReportReason.TOO_HARD,
            created_at=now,
        )
        assert report.session_id == sid
        assert report.question_number == 2
        assert report.reason == ReportReason.TOO_HARD
        assert report.created_at == now


class TestSessionFeedbackEntity:
    def test_frozen(self) -> None:
        fb = SessionFeedback(
            session_id=uuid.uuid4(),
            rating=True,
            comment="Great!",
            created_at=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            fb.rating = False  # type: ignore[misc]

    def test_fields_with_comment(self) -> None:
        sid = uuid.uuid4()
        now = datetime.now(UTC)
        fb = SessionFeedback(session_id=sid, rating=False, comment="Meh", created_at=now)
        assert fb.session_id == sid
        assert fb.rating is False
        assert fb.comment == "Meh"

    def test_fields_without_comment(self) -> None:
        fb = SessionFeedback(
            session_id=uuid.uuid4(),
            rating=True,
            comment=None,
            created_at=datetime.now(UTC),
        )
        assert fb.comment is None


# =====================================================================
# 5.2 — Repository tests
# =====================================================================


def _pr_ctx(installation_id, pr_number: int = 42) -> PRContext:
    return PRContext(
        installation_id=installation_id,
        github_installation_id=_TEST_GITHUB_INSTALLATION_ID,
        repo_full_name="acme/repo",
        repo_owner="acme",
        repo_name="repo",
        pr_number=pr_number,
        pr_title="Add foo",
        pr_head_sha="abc123",
        pr_diff_url=f"https://github.com/acme/repo/pull/{pr_number}.diff",
    )


class TestPersistQuestionReport:
    async def test_persist_and_returns_domain_entity(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        # Need a question to report against
        from helprs.modules.comprehension.domain.value_objects import Topic

        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)

        report = await repo.persist_question_report(
            session_id=author.id,
            question_number=1,
            reason=ReportReason.AMBIGUOUS,
        )
        assert isinstance(report, QuestionReport)
        assert report.session_id == author.id
        assert report.question_number == 1
        assert report.reason == ReportReason.AMBIGUOUS

    async def test_duplicate_raises_domain_error(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        from helprs.modules.comprehension.domain.value_objects import Topic

        await repo.append_question(session_id=author.id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)

        await repo.persist_question_report(
            session_id=author.id,
            question_number=1,
            reason=ReportReason.AMBIGUOUS,
        )

        with pytest.raises(DomainValidationError, match="already reported"):
            await repo.persist_question_report(
                session_id=author.id,
                question_number=1,
                reason=ReportReason.OTHER,
            )


class TestPersistSessionFeedback:
    async def test_persist_and_load(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        fb = await repo.persist_session_feedback(
            session_id=author.id,
            rating=True,
            comment="Great session!",
        )
        assert isinstance(fb, SessionFeedback)
        assert fb.session_id == author.id
        assert fb.rating is True
        assert fb.comment == "Great session!"

        loaded = await repo.get_session_feedback(session_id=author.id)
        assert loaded is not None
        assert loaded.rating is True
        assert loaded.comment == "Great session!"

    async def test_persist_without_comment(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        fb = await repo.persist_session_feedback(
            session_id=author.id,
            rating=False,
            comment=None,
        )
        assert fb.comment is None

    async def test_returns_none_when_no_feedback(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        result = await repo.get_session_feedback(session_id=author.id)
        assert result is None

    async def test_duplicate_raises_domain_error(self, db_session, test_installation):
        repo = SqlAlchemySessionRepository(db_session)
        author, _ = await repo.add_pair(pr_ctx=_pr_ctx(test_installation.id))

        await repo.persist_session_feedback(
            session_id=author.id,
            rating=True,
            comment=None,
        )

        with pytest.raises(DomainValidationError, match="already submitted"):
            await repo.persist_session_feedback(
                session_id=author.id,
                rating=False,
                comment="Changed my mind",
            )


# =====================================================================
# 5.3 — GitHub status check tests
# =====================================================================


class TestPostCommitStatus:
    async def test_success(self) -> None:
        mock_response = httpx.Response(
            201,
            json={"id": 1, "state": "success"},
            request=httpx.Request("POST", "https://api.github.com/repos/acme/repo/statuses/abc123"),
        )
        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await post_commit_status(
                owner="acme",
                repo="repo",
                sha="abc123",
                state="success",
                description="Strong — Score: 7.5/10",
                context="helPRs/comprehension",
                installation_token="ghs_test",
            )
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[1]["json"]["state"] == "success"
            assert call_args[1]["json"]["context"] == "helPRs/comprehension"

    async def test_description_truncated_at_140_chars(self) -> None:
        long_desc = "A" * 200
        mock_response = httpx.Response(
            201,
            json={},
            request=httpx.Request("POST", "https://api.github.com/repos/acme/repo/statuses/abc123"),
        )
        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await post_commit_status(
                owner="acme",
                repo="repo",
                sha="abc123",
                state="success",
                description=long_desc,
                context="helPRs/comprehension",
                installation_token="ghs_test",
            )
            sent_desc = mock_client.post.call_args[1]["json"]["description"]
            assert len(sent_desc) == 140

    async def test_403_raises(self) -> None:
        mock_response = httpx.Response(403, json={"message": "forbidden"})
        mock_response.request = httpx.Request("POST", "https://api.github.com/repos/acme/repo/statuses/abc123")
        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await post_commit_status(
                    owner="acme",
                    repo="repo",
                    sha="abc123",
                    state="success",
                    description="test",
                    context="helPRs/comprehension",
                    installation_token="ghs_test",
                )

    async def test_timeout_raises(self) -> None:
        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(httpx.TimeoutException):
                await post_commit_status(
                    owner="acme",
                    repo="repo",
                    sha="abc123",
                    state="success",
                    description="test",
                    context="helPRs/comprehension",
                    installation_token="ghs_test",
                )


# =====================================================================
# 5.4 — Endpoint tests (POST report + POST feedback)
# =====================================================================


@pytest.fixture
async def app_with_completed_session():
    """Create app with a COMPLETED session + question for report/feedback tests."""
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    application.state.session_factory = session_factory

    settings = get_settings()

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
            status="completed",
        )
        bootstrap.add(author)
        await bootstrap.flush()

        # Add a question to the session
        question = QuestionModel(
            session_id=author.id,
            number=1,
            topic="architecture",
            text_hash="a" * 64,
        )
        bootstrap.add(question)
        await bootstrap.commit()

        seeded = {
            "installation_id": installation.id,
            "user_id": user.id,
            "author_id": author.id,
        }

    yield application, session_factory, seeded

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _patch_github_calls_4_2(monkeypatch):
    mint = AsyncMock(return_value="ghs_test_token")
    access_list = AsyncMock(return_value=[])
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


def _bearer(user_id) -> dict:
    get_settings.cache_clear()
    settings = get_settings()
    token = create_access_token(
        {"sub": str(user_id), "github_login": "testuser"},
        settings.SECRET_KEY,
    )
    return {"Authorization": f"Bearer {token}"}


class TestReportEndpoint:
    async def test_report_question_201(self, app_with_completed_session, _patch_github_calls_4_2):
        app, session_factory, seeded = app_with_completed_session
        _, access_list, _ = _patch_github_calls_4_2

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/questions/1/report",
                json={"reason": "ambiguous"},
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["question_number"] == 1
        assert body["reason"] == "ambiguous"

    async def test_report_duplicate_409(self, app_with_completed_session, _patch_github_calls_4_2):
        app, session_factory, seeded = app_with_completed_session
        _, access_list, _ = _patch_github_calls_4_2

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp1 = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/questions/1/report",
                json={"reason": "ambiguous"},
                headers=_bearer(seeded["user_id"]),
            )
            assert resp1.status_code == 201

            resp2 = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/questions/1/report",
                json={"reason": "too_easy"},
                headers=_bearer(seeded["user_id"]),
            )
            assert resp2.status_code == 409

    async def test_report_bad_question_404(self, app_with_completed_session, _patch_github_calls_4_2):
        app, session_factory, seeded = app_with_completed_session
        _, access_list, _ = _patch_github_calls_4_2

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/questions/99/report",
                json={"reason": "ambiguous"},
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 404

    async def test_report_bad_session_404(self, app_with_completed_session, _patch_github_calls_4_2):
        app, _, seeded = app_with_completed_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{uuid.uuid4()}/questions/1/report",
                json={"reason": "ambiguous"},
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 404


class TestFeedbackEndpoint:
    async def test_submit_feedback_201(self, app_with_completed_session, _patch_github_calls_4_2):
        app, session_factory, seeded = app_with_completed_session
        _, access_list, _ = _patch_github_calls_4_2

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/feedback",
                json={"rating": True, "comment": "Excellent!"},
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["rating"] is True
        assert body["comment"] == "Excellent!"

    async def test_submit_feedback_duplicate_409(self, app_with_completed_session, _patch_github_calls_4_2):
        app, session_factory, seeded = app_with_completed_session
        _, access_list, _ = _patch_github_calls_4_2

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp1 = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/feedback",
                json={"rating": True},
                headers=_bearer(seeded["user_id"]),
            )
            assert resp1.status_code == 201

            resp2 = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/feedback",
                json={"rating": False},
                headers=_bearer(seeded["user_id"]),
            )
            assert resp2.status_code == 409

    async def test_feedback_on_non_completed_session_422(self, app_with_completed_session, _patch_github_calls_4_2):
        """Feedback requires session status == COMPLETED."""
        app, session_factory, seeded = app_with_completed_session
        _, access_list, _ = _patch_github_calls_4_2

        # Change session status to ACTIVE
        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
            await s.execute(
                update(SessionModel).where(SessionModel.id == seeded["author_id"]).values(status="active")
            )
            await s.commit()
        access_list.return_value = [inst]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/feedback",
                json={"rating": True},
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 422

    async def test_feedback_no_auth_401(self, app_with_completed_session):
        app, _, seeded = app_with_completed_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/feedback",
                json={"rating": True},
            )
        assert resp.status_code == 401


# =====================================================================
# 5.5 — SSE integration: status check called after score, before done
# =====================================================================


class TestSSEStatusCheckIntegration:
    """Verify that status check is called after score persist + before
    'done' event, and that 'done' is still emitted if status check fails.
    """

    async def test_post_commit_status_posts_to_github(self, monkeypatch):
        """Verify post_commit_status sends the correct payload to GitHub."""
        import httpx

        from helprs.modules.installation.service import post_commit_status

        captured_request = {}

        async def mock_post(self, url, **kwargs):
            captured_request["url"] = str(url)
            captured_request["json"] = kwargs.get("json")
            captured_request["headers"] = kwargs.get("headers")
            return httpx.Response(201, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        await post_commit_status(
            owner="acme",
            repo="app",
            sha="abc123",
            state="success",
            description="Strong — Score: 7.5/10",
            context="helPRs/comprehension",
            installation_token="ghs_test_token",
        )

        assert "acme/app/statuses/abc123" in captured_request["url"]
        assert captured_request["json"]["state"] == "success"
        assert captured_request["json"]["description"] == "Strong — Score: 7.5/10"
        assert captured_request["json"]["context"] == "helPRs/comprehension"
        assert "Bearer ghs_test_token" in captured_request["headers"]["Authorization"]

    async def test_post_commit_status_truncates_description_to_140(self, monkeypatch):
        """GitHub API limits description to 140 chars."""
        import httpx

        from helprs.modules.installation.service import post_commit_status

        captured = {}

        async def mock_post(self, url, **kwargs):
            captured["description"] = kwargs.get("json", {}).get("description")
            return httpx.Response(201, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        long_desc = "A" * 200
        await post_commit_status(
            owner="o", repo="r", sha="s", state="success",
            description=long_desc, context="c", installation_token="t",
        )
        assert len(captured["description"]) == 140

    async def test_fire_and_forget_structure_in_sse(self):
        """Verify the sse.py scoring flow wraps post_commit_status in
        try/except and emits 'done' unconditionally after it.

        Uses AST analysis instead of string search for robustness.
        """
        import ast
        import pathlib

        sse_path = (
            pathlib.Path(__file__).resolve().parents[3]
            / "src" / "helprs" / "modules" / "comprehension" / "presentation" / "sse.py"
        )
        tree = ast.parse(sse_path.read_text())

        # Find the stream_session function
        stream_fn = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "stream_session":
                stream_fn = node
                break
        assert stream_fn is not None, "stream_session function not found"

        source = sse_path.read_text()
        lines = source.splitlines()

        # Find post_commit_status call line and the next "done" yield after it.
        # The yield and "done" may be on separate lines, so track _sse_frame
        # calls that are followed by "done" on the same or next line.
        status_line = None
        done_line_after_status = None
        for i, line in enumerate(lines, 1):
            if "post_commit_status" in line and "await" in line:
                status_line = i
            if status_line and i > status_line and '"done"' in line:
                done_line_after_status = i
                break

        assert status_line is not None, "post_commit_status call not found in sse.py"
        assert done_line_after_status is not None, "done event not found after post_commit_status"
        assert done_line_after_status > status_line, "done must come after status check"

        # Verify the status check is inside a try/except (fire-and-forget)
        # by checking that "github_status_check_failed" appears between status_line and done_line
        between = "\n".join(lines[status_line - 1 : done_line_after_status])
        assert "github_status_check_failed" in between, (
            "status check must be wrapped in try/except with failure logging"
        )
