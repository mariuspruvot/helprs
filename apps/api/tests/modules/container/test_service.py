"""Tests for container service functions using test doubles."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.database import Base
from helprs.modules.container.models import ContainerStatus
from helprs.modules.container.service import (
    CONTAINER_TTL_SECONDS,
    ContainerInfo,
    cleanup_expired,
    create_session,
    get_session,
    get_session_or_404,
    mark_completed,
    reconcile_on_startup,
    start_container,
    stop_container,
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
        listed_containers: list[ContainerInfo] | None = None,
        fail_on_list: bool = False,
    ):
        self._container_id = container_id
        self._exit_code = exit_code
        self._fail_on_create = fail_on_create
        self._fail_on_stop = fail_on_stop
        self._fail_on_list = fail_on_list
        self._log_lines = log_lines or ["line 1", "line 2"]
        self._listed_containers = listed_containers or []
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

    async def list_containers(self, label_filter: str) -> list[ContainerInfo]:
        if self._fail_on_list:
            raise RuntimeError("Docker daemon unreachable")
        return self._listed_containers


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
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


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


class TestStreamOutput:
    async def test_yields_sse_events(self):
        docker = FakeDockerClient(log_lines=["hello world", "done"])
        lines = []
        async for event in stream_output(docker, "container-123"):
            lines.append(event)
        assert lines == ["data: hello world\n\n", "data: done\n\n"]


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
# Tests: reconcile_on_startup
# ---------------------------------------------------------------------------


class TestReconcileOnStartup:
    async def test_removes_orphan_docker_containers(self, db: AsyncSession, installation: Installation):
        """Docker container exists but has no matching active DB session."""
        orphan = ContainerInfo(
            container_id="orphan-container-123",
            labels={"helprs.session_id": str(uuid.uuid4())},
        )
        docker = FakeDockerClient(listed_containers=[orphan])

        containers_removed, sessions_updated = await reconcile_on_startup(db, docker)

        assert containers_removed == 1
        assert sessions_updated == 0
        assert "orphan-container-123" in docker.stopped
        assert "orphan-container-123" in docker.removed

    async def test_marks_stale_sessions_failed(self, db: AsyncSession, installation: Installation):
        """DB session is RUNNING but its container_id is not in Docker."""
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs.status = ContainerStatus.RUNNING
        cs.container_id = "vanished-container-456"
        await db.flush()

        docker = FakeDockerClient(listed_containers=[])

        containers_removed, sessions_updated = await reconcile_on_startup(db, docker)

        assert sessions_updated == 1
        refreshed = await get_session(db, cs.id)
        assert refreshed is not None
        assert refreshed.status == ContainerStatus.FAILED
        assert refreshed.completed_at is not None

    async def test_marks_expired_sessions_timeout(self, db: AsyncSession, installation: Installation):
        """DB session is RUNNING and past TTL, with container still in Docker."""
        from datetime import UTC, datetime, timedelta

        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs.status = ContainerStatus.RUNNING
        cs.container_id = "expired-container-789"
        cs.created_at = datetime.now(UTC) - timedelta(seconds=CONTAINER_TTL_SECONDS + 120)
        await db.flush()

        container_info = ContainerInfo(
            container_id="expired-container-789",
            labels={"helprs.session_id": str(cs.id)},
        )
        docker = FakeDockerClient(listed_containers=[container_info])

        containers_removed, sessions_updated = await reconcile_on_startup(db, docker)

        assert containers_removed == 1
        assert sessions_updated == 1
        refreshed = await get_session(db, cs.id)
        assert refreshed is not None
        assert refreshed.status == ContainerStatus.TIMEOUT
        assert "expired-container-789" in docker.stopped

    async def test_marks_stuck_pending_failed(self, db: AsyncSession, installation: Installation):
        """DB session stuck in PENDING with no container_id."""
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        # create_session already sets PENDING and container_id=None
        docker = FakeDockerClient(listed_containers=[])

        containers_removed, sessions_updated = await reconcile_on_startup(db, docker)

        assert sessions_updated == 1
        refreshed = await get_session(db, cs.id)
        assert refreshed is not None
        assert refreshed.status == ContainerStatus.FAILED

    async def test_leaves_valid_sessions_untouched(self, db: AsyncSession, installation: Installation):
        """RUNNING session with recent created_at and matching Docker container."""
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=1,
            repo_full_name="org/repo",
            skill_name="challenge-me",
        )
        cs.status = ContainerStatus.RUNNING
        cs.container_id = "active-container-abc"
        await db.flush()

        container_info = ContainerInfo(
            container_id="active-container-abc",
            labels={"helprs.session_id": str(cs.id)},
        )
        docker = FakeDockerClient(listed_containers=[container_info])

        containers_removed, sessions_updated = await reconcile_on_startup(db, docker)

        assert containers_removed == 0
        assert sessions_updated == 0
        refreshed = await get_session(db, cs.id)
        assert refreshed is not None
        assert refreshed.status == ContainerStatus.RUNNING

    async def test_handles_docker_unreachable(self, db: AsyncSession):
        """list_containers failure returns (0, 0) without crashing."""
        docker = FakeDockerClient(fail_on_list=True)

        containers_removed, sessions_updated = await reconcile_on_startup(db, docker)

        assert containers_removed == 0
        assert sessions_updated == 0

    async def test_noop_on_empty_state(self, db: AsyncSession):
        """No sessions, no containers -> (0, 0)."""
        docker = FakeDockerClient(listed_containers=[])

        containers_removed, sessions_updated = await reconcile_on_startup(db, docker)

        assert containers_removed == 0
        assert sessions_updated == 0
