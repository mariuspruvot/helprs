"""Tests for container router endpoints.

Uses test doubles for the service layer -- no real Docker or DB required
for these endpoint tests (FastAPI integration tests with ASGI transport).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base, clear_session_factory, set_session_factory
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.main import create_app
from helprs.modules.container.models import ContainerSession, ContainerStatus
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import BYOKConfig, Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


@pytest.fixture
async def app_with_db():
    """Create app with a real test database."""
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    application.state.session_factory = session_factory
    set_session_factory(session_factory)

    yield application

    clear_session_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def seeded_app(app_with_db):
    """Seed the database with a user, installation, and BYOK config."""
    settings = get_settings()
    session_factory = app_with_db.state.session_factory

    async with session_factory() as session:
        encrypted_token = fernet_encrypt("gho_test_token", settings.FERNET_KEY)
        user = GitHubUser(
            github_id=88888888,
            github_login="container-test-user",
            email="container@test.com",
            avatar_url=None,
            github_access_token_enc=encrypted_token,
        )
        session.add(user)
        await session.flush()

        installation = Installation(
            github_installation_id=77777777,
            account_login="test-org",
            account_id=88888888,
            account_type="User",
            repository_selection="all",
            app_slug="helprs-test",
            target_type="User",
        )
        session.add(installation)
        await session.flush()

        byok = BYOKConfig(
            installation_id=installation.id,
            encrypted_api_key=fernet_encrypt("sk-ant-test1234567890", settings.FERNET_KEY),
            key_status="valid",
            validated_at=datetime.now(UTC),
            key_hint="...7890",
        )
        session.add(byok)
        await session.flush()

        access_token = create_access_token(
            {"sub": str(user.id), "github_login": user.github_login},
            settings.SECRET_KEY,
        )
        await session.commit()

    return {
        "app": app_with_db,
        "user_id": user.id,
        "installation_id": installation.id,
        "access_token": access_token,
    }


class FakeDockerClientForRouter:
    """Minimal fake that is injected via monkeypatch."""

    def __init__(self, log_lines: list[str] | None = None, exit_code: int = 0):
        self.container_id = "fake-router-container-id"
        self._log_lines = log_lines or ['{"type":"system","subtype":"init"}\n', '{"type":"assistant","message":{}}\n']
        self._exit_code = exit_code

    async def create_container(self, image, environment, volumes, labels):
        return self.container_id

    async def start_container(self, container_id):
        pass

    async def stop_container(self, container_id):
        pass

    async def remove_container(self, container_id, force=False):
        pass

    async def container_logs(self, container_id, follow=False) -> AsyncIterator[str]:
        for line in self._log_lines:
            yield line

    async def write_to_container(self, container_id, data):
        pass

    async def wait_container(self, container_id):
        return self._exit_code

    async def close(self):
        pass


class TestCreateSession:
    async def test_create_session_returns_201(self, seeded_app, tmp_path: Path):
        app = seeded_app["app"]
        token = seeded_app["access_token"]
        installation_id = seeded_app["installation_id"]

        # Create a temporary skills directory
        (tmp_path / "challenge-me").mkdir()
        (tmp_path / "challenge-me" / "prompt.md").write_text("test")

        # Patch the Docker client, mint_installation_token, and SKILLS_BASE_PATH
        with (
            patch(
                "helprs.modules.container.router._get_docker_client",
                return_value=FakeDockerClientForRouter(),
            ),
            patch(
                "helprs.modules.container.router.mint_installation_token",
                new_callable=AsyncMock,
                return_value="gho_minted_token",
            ),
            patch(
                "helprs.modules.container.service.SKILLS_BASE_PATH",
                tmp_path,
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/api/v1/containers/sessions",
                    json={
                        "installation_id": str(installation_id),
                        "pr_number": 42,
                        "repo_full_name": "org/repo",
                        "skill_name": "challenge-me",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "running"
        assert data["pr_number"] == 42
        assert data["repo_full_name"] == "org/repo"
        assert data["skill_name"] == "challenge-me"

    async def test_create_session_missing_installation(self, seeded_app):
        app = seeded_app["app"]
        token = seeded_app["access_token"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/containers/sessions",
                json={
                    "installation_id": str(uuid.uuid4()),
                    "pr_number": 1,
                    "repo_full_name": "org/repo",
                    "skill_name": "challenge-me",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 404

    async def test_create_session_invalid_repo_format(self, seeded_app):
        app = seeded_app["app"]
        token = seeded_app["access_token"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/containers/sessions",
                json={
                    "installation_id": str(seeded_app["installation_id"]),
                    "pr_number": 1,
                    "repo_full_name": "invalid-format",
                    "skill_name": "challenge-me",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 422


class TestGetSession:
    async def test_get_session_not_found(self, seeded_app):
        app = seeded_app["app"]
        token = seeded_app["access_token"]
        fake_id = uuid.uuid4()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/containers/sessions/{fake_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 404


class TestStopSession:
    async def test_stop_session_not_found(self, seeded_app):
        app = seeded_app["app"]
        token = seeded_app["access_token"]
        fake_id = uuid.uuid4()

        with patch(
            "helprs.modules.container.router._get_docker_client",
            return_value=FakeDockerClientForRouter(),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/v1/containers/sessions/{fake_id}/stop",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 404


SAMPLE_RESULT_WITH_SCORE = (
    "Some text\n\n---\n\n## Results\n\n**Questions:** 3\n\n"
    "### Score: 8 / 10  ████████░░ Strong\n\n"
    "### Verdict\nReady for review.\n\n---"
)


class TestStreamDoneEvent:
    async def test_stream_emits_done_event_when_container_exits(self, seeded_app):
        """When docker logs end (container exit), the SSE stream must emit an event: done."""
        app = seeded_app["app"]
        token = seeded_app["access_token"]
        installation_id = seeded_app["installation_id"]

        # Create a RUNNING session in the DB via the service layer
        session_factory = app.state.session_factory
        async with session_factory() as session:
            from helprs.modules.container.models import ContainerSession, ContainerStatus

            cs = ContainerSession(
                installation_id=installation_id,
                pr_number=1,
                repo_full_name="org/repo",
                skill_name="challenge-me",
                status=ContainerStatus.RUNNING,
                container_id="fake-router-container-id",
            )
            session.add(cs)
            await session.commit()
            session_id = cs.id

        fake_docker = FakeDockerClientForRouter()

        with patch(
            "helprs.modules.container.router._get_docker_client",
            return_value=fake_docker,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    f"/api/v1/containers/sessions/{session_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        body = resp.text
        # The last SSE frame must be an event: done
        assert "event: done" in body
        assert '"message"' in body

    async def test_stream_marks_session_completed_in_db(self, seeded_app):
        """After the stream ends, the session status should be COMPLETED in the DB."""
        app = seeded_app["app"]
        token = seeded_app["access_token"]
        installation_id = seeded_app["installation_id"]

        session_factory = app.state.session_factory
        async with session_factory() as session:
            from helprs.modules.container.models import ContainerSession, ContainerStatus

            cs = ContainerSession(
                installation_id=installation_id,
                pr_number=2,
                repo_full_name="org/repo",
                skill_name="challenge-me",
                status=ContainerStatus.RUNNING,
                container_id="fake-router-container-id",
            )
            session.add(cs)
            await session.commit()
            session_id = cs.id

        fake_docker = FakeDockerClientForRouter()

        with patch(
            "helprs.modules.container.router._get_docker_client",
            return_value=fake_docker,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.get(
                    f"/api/v1/containers/sessions/{session_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )

        # Verify session is COMPLETED in DB
        async with session_factory() as session:
            from sqlalchemy import select

            result = await session.execute(select(ContainerSession).where(ContainerSession.id == session_id))
            updated = result.scalar_one()
            assert updated.status == ContainerStatus.COMPLETED
            assert updated.completed_at is not None


class TestPostResultsComment:
    """Tests for posting challenge-me results to PR after session completion."""

    async def _create_running_session(self, seeded_app, *, post_results: bool = False, skill: str = "challenge-me"):
        """Helper: create a RUNNING session and optionally enable post_results_to_pr."""
        app = seeded_app["app"]
        installation_id = seeded_app["installation_id"]
        session_factory = app.state.session_factory

        async with session_factory() as session:
            if post_results:
                from sqlalchemy import select

                result = await session.execute(select(Installation).where(Installation.id == installation_id))
                inst = result.scalar_one()
                inst.post_results_to_pr = True
                await session.flush()

            cs = ContainerSession(
                installation_id=installation_id,
                pr_number=99,
                repo_full_name="org/repo",
                skill_name=skill,
                status=ContainerStatus.RUNNING,
                container_id="fake-router-container-id",
            )
            session.add(cs)
            await session.commit()
            return cs.id

    async def _create_result_event(self, seeded_app, session_id: uuid.UUID, result_text: str):
        """Helper: insert a result event into session_events."""
        session_factory = seeded_app["app"].state.session_factory
        async with session_factory() as session:
            from helprs.modules.container.models import SessionEvent

            event = SessionEvent(
                session_id=session_id,
                event_id=100,
                data={"type": "result", "result": result_text},
            )
            session.add(event)
            await session.commit()

    async def test_posts_comment_when_enabled(self, seeded_app):
        """With post_results_to_pr=True, a PR comment should be posted after completion."""
        app = seeded_app["app"]
        token = seeded_app["access_token"]

        session_id = await self._create_running_session(seeded_app, post_results=True)
        await self._create_result_event(seeded_app, session_id, SAMPLE_RESULT_WITH_SCORE)

        fake_docker = FakeDockerClientForRouter()

        with (
            patch("helprs.modules.container.router._get_docker_client", return_value=fake_docker),
            patch(
                "helprs.modules.container.router.mint_installation_token",
                new_callable=AsyncMock,
                return_value="gho_fresh_token",
            ),
            patch(
                "helprs.modules.container.router.post_pr_comment_with_retry",
                new_callable=AsyncMock,
            ) as mock_post,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get(
                    f"/api/v1/containers/sessions/{session_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["owner"] == "org"
        assert call_kwargs["repo"] == "repo"
        assert call_kwargs["pr_number"] == 99
        assert "Score: 8 / 10" in call_kwargs["body"]
        assert "helPRs Challenge-Me Results" in call_kwargs["body"]

    async def test_skips_comment_when_disabled(self, seeded_app):
        """With post_results_to_pr=False (default), no comment should be posted."""
        app = seeded_app["app"]
        token = seeded_app["access_token"]

        session_id = await self._create_running_session(seeded_app, post_results=False)
        await self._create_result_event(seeded_app, session_id, SAMPLE_RESULT_WITH_SCORE)

        fake_docker = FakeDockerClientForRouter()

        with (
            patch("helprs.modules.container.router._get_docker_client", return_value=fake_docker),
            patch(
                "helprs.modules.container.router.post_pr_comment_with_retry",
                new_callable=AsyncMock,
            ) as mock_post,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.get(
                    f"/api/v1/containers/sessions/{session_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )

        mock_post.assert_not_called()

    async def test_skips_comment_on_failed_session(self, seeded_app):
        """When container exits with non-zero, no comment should be posted."""
        app = seeded_app["app"]
        token = seeded_app["access_token"]

        session_id = await self._create_running_session(seeded_app, post_results=True)
        await self._create_result_event(seeded_app, session_id, SAMPLE_RESULT_WITH_SCORE)

        fake_docker = FakeDockerClientForRouter(exit_code=1)

        with (
            patch("helprs.modules.container.router._get_docker_client", return_value=fake_docker),
            patch(
                "helprs.modules.container.router.post_pr_comment_with_retry",
                new_callable=AsyncMock,
            ) as mock_post,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.get(
                    f"/api/v1/containers/sessions/{session_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )

        mock_post.assert_not_called()

    async def test_skips_comment_for_non_challenge_me_skill(self, seeded_app):
        """When skill is not challenge-me, no comment should be posted."""
        app = seeded_app["app"]
        token = seeded_app["access_token"]

        session_id = await self._create_running_session(seeded_app, post_results=True, skill="code-review")
        await self._create_result_event(seeded_app, session_id, SAMPLE_RESULT_WITH_SCORE)

        fake_docker = FakeDockerClientForRouter()

        with (
            patch("helprs.modules.container.router._get_docker_client", return_value=fake_docker),
            patch(
                "helprs.modules.container.router.post_pr_comment_with_retry",
                new_callable=AsyncMock,
            ) as mock_post,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.get(
                    f"/api/v1/containers/sessions/{session_id}/stream",
                    headers={"Authorization": f"Bearer {token}"},
                )

        mock_post.assert_not_called()
