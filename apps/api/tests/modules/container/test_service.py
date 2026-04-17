"""Tests for container service functions using test doubles."""

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.database import Base, clear_session_factory, set_session_factory
from helprs.modules.container.models import ContainerStatus, SessionEvent
from helprs.modules.container.service import (
    CONTAINER_TTL_SECONDS,
    cleanup_expired,
    create_session,
    get_session,
    get_session_events,
    get_session_or_404,
    mark_completed,
    start_container,
    stop_container,
    stream_and_persist,
    stream_events,
    stream_output,
)
from helprs.modules.installation.models import Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


# ---------------------------------------------------------------------------
# Test double for DockerClient
# ---------------------------------------------------------------------------


class FakeDockerClient:
    """Test double implementing the DockerClient protocol."""

    def __init__(
        self,
        container_id: str = "fake-container-abc123",
        exit_code: int = 0,
        fail_on_create: bool = False,
        fail_on_stop: bool = False,
        log_lines: list[str] | None = None,
    ):
        self._container_id = container_id
        self._exit_code = exit_code
        self._fail_on_create = fail_on_create
        self._fail_on_stop = fail_on_stop
        self._log_lines = log_lines or ["line 1\n", "line 2\n"]
        self.created: list[dict] = []
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.removed: list[str] = []

    async def create_container(
        self,
        image: str,
        environment: dict[str, str],
        volumes: list[str],
        labels: dict[str, str],
    ) -> str:
        if self._fail_on_create:
            raise RuntimeError("Docker daemon unreachable")
        self.created.append({"image": image, "environment": environment, "volumes": volumes, "labels": labels})
        return self._container_id

    async def start_container(self, container_id: str) -> None:
        self.started.append(container_id)

    async def stop_container(self, container_id: str) -> None:
        if self._fail_on_stop:
            raise RuntimeError("Container already stopped")
        self.stopped.append(container_id)

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        self.removed.append(container_id)

    async def container_logs(self, container_id: str, follow: bool = False) -> AsyncIterator[str]:
        for line in self._log_lines:
            yield line

    async def wait_container(self, container_id: str) -> int:
        return self._exit_code


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def db(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def db_with_factory(engine):
    """DB session + registers the factory for get_db_context (needed by stream_and_persist)."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    set_session_factory(factory)
    async with factory() as session:
        yield session, factory
        await session.rollback()
    clear_session_factory()


@pytest.fixture
async def installation(db: AsyncSession) -> Installation:
    inst = Installation(
        github_installation_id=99999999,
        account_login="test-org",
        account_id=11111,
        account_type="Organization",
        repository_selection="all",
        app_slug="helprs-test",
        target_type="Organization",
    )
    db.add(inst)
    await db.flush()
    return inst


@pytest.fixture
def docker() -> FakeDockerClient:
    return FakeDockerClient()


@pytest.fixture
def skills_path(tmp_path: Path) -> Path:
    """Create a temporary skills directory with test skill folders."""
    for skill in ("challenge-me", "code-review"):
        (tmp_path / skill).mkdir()
        (tmp_path / skill / "prompt.md").write_text("test prompt")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    async def test_creates_session_in_pending(self, db: AsyncSession, installation: Installation):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=42,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        assert cs.status == ContainerStatus.PENDING
        assert cs.pr_number == 42
        assert cs.repo_full_name == "org/repo"
        assert cs.skill_name == "challenge-me"
        assert cs.container_id is None
        assert cs.installation_id == installation.id

    async def test_creates_session_with_null_user_id(self, db: AsyncSession, installation: Installation):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="code-review",
        )
        assert cs.user_id is None


# ---------------------------------------------------------------------------
# Tests: get_session
# ---------------------------------------------------------------------------


class TestGetSession:
    async def test_returns_none_for_missing(self, db: AsyncSession):
        result = await get_session(db, uuid.uuid4())
        assert result is None

    async def test_returns_session(self, db: AsyncSession, installation: Installation):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        found = await get_session(db, cs.id)
        assert found is not None
        assert found.id == cs.id


class TestGetSessionOr404:
    async def test_raises_not_found(self, db: AsyncSession):
        from helprs.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await get_session_or_404(db, uuid.uuid4())


# ---------------------------------------------------------------------------
# Tests: start_container
# ---------------------------------------------------------------------------


class TestStartContainer:
    async def test_starts_container_and_transitions_to_running(
        self,
        db: AsyncSession,
        installation: Installation,
        docker: FakeDockerClient,
        skills_path: Path,
    ):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=10,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        result = await start_container(
            db=db,
            session_id=cs.id,
            docker=docker,
            claude_oauth_token="test-oauth-token",
            github_token="gho_test",
            skills_base_path=skills_path,
        )
        assert result.status == ContainerStatus.RUNNING
        assert result.container_id == "fake-container-abc123"
        assert result.started_at is not None
        assert len(docker.created) == 1
        assert len(docker.started) == 1

    async def test_injects_correct_environment(
        self,
        db: AsyncSession,
        installation: Installation,
        docker: FakeDockerClient,
        skills_path: Path,
    ):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=7,
            repo_full_name="myorg/myrepo",
            skill_name="code-review",
        )
        await start_container(
            db=db,
            session_id=cs.id,
            docker=docker,
            claude_oauth_token="test-oauth-key123",
            github_token="gho_tok456",
            skills_base_path=skills_path,
        )
        env = docker.created[0]["environment"]
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "test-oauth-key123"
        assert env["GITHUB_TOKEN"] == "gho_tok456"
        assert env["PR_NUMBER"] == "7"
        assert env["REPO_FULL_NAME"] == "myorg/myrepo"
        assert env["SKILL_NAME"] == "code-review"

    async def test_fails_on_docker_error(
        self,
        db: AsyncSession,
        installation: Installation,
        skills_path: Path,
    ):
        from helprs.core.exceptions import ExternalServiceError

        failing_docker = FakeDockerClient(fail_on_create=True)
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        with pytest.raises(ExternalServiceError, match="Failed to start container"):
            await start_container(
                db=db,
                session_id=cs.id,
                docker=failing_docker,
                claude_oauth_token="test-oauth-token",
                github_token="gho_test",
                skills_base_path=skills_path,
            )
        # Session should be marked as failed
        refreshed = await get_session(db, cs.id)
        assert refreshed is not None
        assert refreshed.status == ContainerStatus.FAILED

    async def test_fails_on_missing_skill(
        self,
        db: AsyncSession,
        installation: Installation,
        skills_path: Path,
    ):
        from helprs.core.exceptions import NotFoundError

        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="nonexistent-skill",
        )
        with pytest.raises(NotFoundError, match="Skill 'nonexistent-skill' not found"):
            await start_container(
                db=db,
                session_id=cs.id,
                docker=FakeDockerClient(),
                claude_oauth_token="test-oauth-token",
                github_token="gho_test",
                skills_base_path=skills_path,
            )

    async def test_rejects_non_pending_session(
        self,
        db: AsyncSession,
        installation: Installation,
        docker: FakeDockerClient,
        skills_path: Path,
    ):
        from helprs.core.exceptions import ExternalServiceError

        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs.status = ContainerStatus.RUNNING
        await db.flush()

        with pytest.raises(ExternalServiceError, match="Cannot start session"):
            await start_container(
                db=db,
                session_id=cs.id,
                docker=docker,
                claude_oauth_token="test-oauth-token",
                github_token="gho_test",
                skills_base_path=skills_path,
            )


# ---------------------------------------------------------------------------
# Tests: stream_output
# ---------------------------------------------------------------------------


class TestStreamEvents:
    async def test_yields_event_id_and_line(self):
        docker = FakeDockerClient(log_lines=["line1\n", "line2\n"])
        events = []
        async for event_id, line in stream_events(docker, "cid"):
            events.append((event_id, line))
        assert events == [(1, "line1"), (2, "line2")]

    async def test_skips_blank_lines(self):
        docker = FakeDockerClient(log_lines=["\n", "data\n", "\n"])
        events = []
        async for event_id, line in stream_events(docker, "cid"):
            events.append((event_id, line))
        assert events == [(1, "data")]

    async def test_buffers_partial_lines(self):
        docker = FakeDockerClient(log_lines=["hel", "lo\nworld\n"])
        events = []
        async for event_id, line in stream_events(docker, "cid"):
            events.append((event_id, line))
        assert events == [(1, "hello"), (2, "world")]


class TestStreamOutput:
    async def test_yields_sse_events(self):
        docker = FakeDockerClient(log_lines=["hello world\n", "done\n"])
        lines = []
        async for event in stream_output(docker, "container-123"):
            lines.append(event)
        assert lines == [
            "id: 1\ndata: hello world\n\n",
            "id: 2\ndata: done\n\n",
        ]

    async def test_respects_offset(self):
        docker = FakeDockerClient(log_lines=["first\n", "second\n", "third\n"])
        lines = []
        async for event in stream_output(docker, "cid", offset=2):
            lines.append(event)
        assert lines == ["id: 3\ndata: third\n\n"]


# ---------------------------------------------------------------------------
# Tests: stop_container
# ---------------------------------------------------------------------------


class TestStopContainer:
    async def test_stops_running_container(
        self,
        db: AsyncSession,
        installation: Installation,
        docker: FakeDockerClient,
        skills_path: Path,
    ):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs = await start_container(
            db=db,
            session_id=cs.id,
            docker=docker,
            claude_oauth_token="test-oauth-token",
            github_token="gho_test",
            skills_base_path=skills_path,
        )
        result = await stop_container(db=db, session_id=cs.id, docker=docker)
        assert result.status == ContainerStatus.COMPLETED
        assert result.completed_at is not None

    async def test_noop_for_completed_session(
        self,
        db: AsyncSession,
        installation: Installation,
        docker: FakeDockerClient,
    ):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs.status = ContainerStatus.COMPLETED
        await db.flush()

        result = await stop_container(db=db, session_id=cs.id, docker=docker)
        assert result.status == ContainerStatus.COMPLETED
        assert len(docker.stopped) == 0

    async def test_handles_docker_stop_failure_gracefully(
        self,
        db: AsyncSession,
        installation: Installation,
    ):
        docker = FakeDockerClient(fail_on_stop=True)
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs.status = ContainerStatus.RUNNING
        cs.container_id = "fake-container-abc123"
        await db.flush()

        result = await stop_container(db=db, session_id=cs.id, docker=docker)
        assert result.status == ContainerStatus.COMPLETED


# ---------------------------------------------------------------------------
# Tests: mark_completed
# ---------------------------------------------------------------------------


class TestMarkCompleted:
    async def test_marks_success_on_zero_exit(
        self,
        db: AsyncSession,
        installation: Installation,
        docker: FakeDockerClient,
        skills_path: Path,
    ):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs = await start_container(
            db=db,
            session_id=cs.id,
            docker=docker,
            claude_oauth_token="test-oauth-token",
            github_token="gho_test",
            skills_base_path=skills_path,
        )
        result = await mark_completed(db=db, session_id=cs.id, docker=docker)
        assert result.status == ContainerStatus.COMPLETED
        assert result.completed_at is not None

    async def test_marks_failed_on_nonzero_exit(
        self,
        db: AsyncSession,
        installation: Installation,
        skills_path: Path,
    ):
        docker = FakeDockerClient(exit_code=1)
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs = await start_container(
            db=db,
            session_id=cs.id,
            docker=docker,
            claude_oauth_token="test-oauth-token",
            github_token="gho_test",
            skills_base_path=skills_path,
        )
        result = await mark_completed(db=db, session_id=cs.id, docker=docker)
        assert result.status == ContainerStatus.FAILED


# ---------------------------------------------------------------------------
# Tests: cleanup_expired
# ---------------------------------------------------------------------------


class TestCleanupExpired:
    async def test_cleans_expired_sessions(
        self,
        db: AsyncSession,
        installation: Installation,
        docker: FakeDockerClient,
    ):
        from datetime import UTC, datetime, timedelta

        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        # Backdate and set running via ORM so the session sees the update
        cs.created_at = datetime.now(UTC) - timedelta(seconds=CONTAINER_TTL_SECONDS + 120)
        cs.status = ContainerStatus.RUNNING
        await db.flush()

        cleaned = await cleanup_expired(db=db, docker=docker)
        assert cleaned == 1

    async def test_skips_completed_sessions(
        self,
        db: AsyncSession,
        installation: Installation,
        docker: FakeDockerClient,
    ):
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs.status = ContainerStatus.COMPLETED
        await db.flush()

        cleaned = await cleanup_expired(db=db, docker=docker)
        assert cleaned == 0


# ---------------------------------------------------------------------------
# Tests: stream_and_persist
# ---------------------------------------------------------------------------


class TestStreamAndPersist:
    async def test_persists_events_to_db(self, engine, db_with_factory):
        db, factory = db_with_factory
        inst = Installation(
            github_installation_id=77777777,
            account_login="persist-org",
            account_id=22222,
            account_type="Organization",
            repository_selection="all",
            app_slug="helprs-test",
            target_type="Organization",
        )
        db.add(inst)
        await db.flush()

        cs = await create_session(db, inst.id, 1, "org/repo", "challenge-me")
        cs.status = ContainerStatus.RUNNING
        cs.container_id = "fake-cid"
        await db.flush()
        await db.commit()

        event_data = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}})
        docker = FakeDockerClient(log_lines=[f"{event_data}\n"])

        sse_events = []
        async for sse in stream_and_persist(docker, "fake-cid", cs.id):
            sse_events.append(sse)

        assert len(sse_events) == 1
        assert "data:" in sse_events[0]

        async with factory() as verify_db:
            result = await verify_db.execute(select(SessionEvent).where(SessionEvent.session_id == cs.id))
            stored = list(result.scalars().all())
            assert len(stored) == 1
            assert stored[0].event_id == 1
            assert stored[0].data["type"] == "assistant"

    async def test_skips_sse_for_offset_but_persists(self, engine, db_with_factory):
        db, factory = db_with_factory
        inst = Installation(
            github_installation_id=77777778,
            account_login="offset-org",
            account_id=22223,
            account_type="Organization",
            repository_selection="all",
            app_slug="helprs-test",
            target_type="Organization",
        )
        db.add(inst)
        await db.flush()

        cs = await create_session(db, inst.id, 1, "org/repo", "challenge-me")
        cs.status = ContainerStatus.RUNNING
        cs.container_id = "fake-cid"
        await db.flush()
        await db.commit()

        docker = FakeDockerClient(
            log_lines=[
                '{"type":"system","subtype":"init"}\n',
                '{"type":"assistant","message":{"content":[]}}\n',
            ]
        )

        sse_events = []
        async for sse in stream_and_persist(docker, "fake-cid", cs.id, offset=1):
            sse_events.append(sse)

        # Only event 2 should be yielded as SSE
        assert len(sse_events) == 1
        assert "id: 2" in sse_events[0]

        # Both events should be persisted
        async with factory() as verify_db:
            result = await verify_db.execute(
                select(SessionEvent).where(SessionEvent.session_id == cs.id).order_by(SessionEvent.event_id)
            )
            stored = list(result.scalars().all())
            assert len(stored) == 2

    async def test_stores_non_json_as_raw(self, engine, db_with_factory):
        db, factory = db_with_factory
        inst = Installation(
            github_installation_id=77777779,
            account_login="raw-org",
            account_id=22224,
            account_type="Organization",
            repository_selection="all",
            app_slug="helprs-test",
            target_type="Organization",
        )
        db.add(inst)
        await db.flush()

        cs = await create_session(db, inst.id, 1, "org/repo", "challenge-me")
        cs.status = ContainerStatus.RUNNING
        cs.container_id = "fake-cid"
        await db.flush()
        await db.commit()

        docker = FakeDockerClient(log_lines=["not-json-content\n"])

        sse_events = []
        async for sse in stream_and_persist(docker, "fake-cid", cs.id):
            sse_events.append(sse)

        async with factory() as verify_db:
            result = await verify_db.execute(select(SessionEvent).where(SessionEvent.session_id == cs.id))
            stored = list(result.scalars().all())
            assert len(stored) == 1
            assert stored[0].data == {"_raw": "not-json-content"}


# ---------------------------------------------------------------------------
# Tests: get_session_events
# ---------------------------------------------------------------------------


class TestGetSessionEvents:
    async def test_returns_events_ordered(self, db: AsyncSession, installation: Installation):
        cs = await create_session(db, installation.id, 1, "org/repo", "challenge-me")
        db.add(SessionEvent(session_id=cs.id, event_id=2, data={"type": "assistant"}))
        db.add(SessionEvent(session_id=cs.id, event_id=1, data={"type": "system"}))
        await db.flush()

        events = await get_session_events(db, cs.id)
        assert len(events) == 2
        assert events[0].event_id == 1
        assert events[1].event_id == 2

    async def test_returns_empty_for_no_events(self, db: AsyncSession, installation: Installation):
        cs = await create_session(db, installation.id, 1, "org/repo", "challenge-me")
        events = await get_session_events(db, cs.id)
        assert events == []

    async def test_raises_404_for_unknown_session(self, db: AsyncSession):
        from helprs.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await get_session_events(db, uuid.uuid4())
