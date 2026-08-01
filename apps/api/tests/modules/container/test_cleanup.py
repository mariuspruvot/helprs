"""Tests for container reaping, with several API workers in play.

Neither ``cleanup_own_running`` nor ``reconcile_stale_sessions`` had any
coverage, which is how both came to be actively destructive to peer workers:
they operated on "every unfinished session" while production runs
``--workers 4`` against one shared Docker socket.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.database import Base
from helprs.modules.container.cleanup import cleanup_own_running, reconcile_stale_sessions
from helprs.modules.container.docker_client import RunnerContainer
from helprs.modules.container.models import ContainerSession, ContainerStatus
from helprs.modules.installation.models import Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"

MY_BOOT = "1000-aaaaaaaa"
PEER_BOOT = "2000-bbbbbbbb"


class FakeDocker:
    """Docker double that knows which containers belong to which process."""

    def __init__(self, runners: dict[str, list[RunnerContainer]] | None = None, alive: set[str] | None = None) -> None:
        self._runners = runners or {}
        self._alive = alive if alive is not None else set()
        self.stopped: list[str] = []
        self.removed: list[str] = []

    async def list_runners(self, *, boot_id: str) -> list[RunnerContainer]:
        return list(self._runners.get(boot_id, []))

    async def container_is_running(self, container_id: str) -> bool:
        return container_id in self._alive

    async def stop_container(self, container_id: str) -> None:
        self.stopped.append(container_id)

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        self.removed.append(container_id)

    # Rest of the protocol, unused here.
    async def create_container(self, image, environment, volumes, labels) -> str: ...
    async def start_container(self, container_id: str) -> None: ...
    def container_logs(self, container_id: str, follow: bool = False) -> AsyncIterator[str]: ...
    async def write_to_container(self, container_id: str, data: str) -> None: ...
    async def wait_container(self, container_id: str) -> int: ...
    async def close(self) -> None: ...


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
async def installation(db: AsyncSession) -> Installation:
    inst = Installation(
        github_installation_id=4242,
        account_login="acme",
        account_id=1,
        account_type="Organization",
        repository_selection="all",
        app_slug="helprs",
        target_type="Organization",
    )
    db.add(inst)
    await db.flush()
    return inst


async def _running_session(db: AsyncSession, installation: Installation, container_id: str) -> ContainerSession:
    cs = ContainerSession(
        installation_id=installation.id,
        pr_number=1,
        repo_full_name="acme/repo",
        skill_name="challenge-me",
        status=ContainerStatus.RUNNING,
        container_id=container_id,
        started_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db.add(cs)
    await db.flush()
    return cs


class TestCleanupOwnRunning:
    async def test_a_peers_session_is_left_alone(self, db, installation):
        """The bug this replaces: one worker shutting down cancelled every
        live session on the host, including three peers' worth."""
        mine = await _running_session(db, installation, "c-mine")
        theirs = await _running_session(db, installation, "c-theirs")
        docker = FakeDocker(
            runners={
                MY_BOOT: [RunnerContainer("c-mine", mine.id)],
                PEER_BOOT: [RunnerContainer("c-theirs", theirs.id)],
            }
        )

        stopped = await cleanup_own_running(db, docker, boot_id=MY_BOOT)

        assert stopped == 1
        assert docker.stopped == ["c-mine"]
        assert mine.status == ContainerStatus.CANCELLED
        assert theirs.status == ContainerStatus.RUNNING
        assert theirs.completed_at is None

    async def test_stops_nothing_when_this_worker_started_nothing(self, db, installation):
        theirs = await _running_session(db, installation, "c-theirs")
        docker = FakeDocker(runners={PEER_BOOT: [RunnerContainer("c-theirs", theirs.id)]})

        assert await cleanup_own_running(db, docker, boot_id=MY_BOOT) == 0
        assert docker.stopped == []
        assert theirs.status == ContainerStatus.RUNNING

    async def test_an_already_finished_session_is_not_recancelled(self, db, installation):
        """A container can outlive its row's completion; overwriting a
        COMPLETED status with CANCELLED would rewrite history."""
        cs = await _running_session(db, installation, "c-done")
        cs.status = ContainerStatus.COMPLETED
        cs.completed_at = datetime.now(UTC)
        await db.flush()
        docker = FakeDocker(runners={MY_BOOT: [RunnerContainer("c-done", cs.id)]})

        assert await cleanup_own_running(db, docker, boot_id=MY_BOOT) == 0
        assert cs.status == ContainerStatus.COMPLETED

    async def test_a_container_whose_row_vanished_is_skipped(self, db, installation):
        docker = FakeDocker(runners={MY_BOOT: [RunnerContainer("c-orphan", uuid.uuid4())]})

        assert await cleanup_own_running(db, docker, boot_id=MY_BOOT) == 0


class TestReconcileStaleSessions:
    async def test_a_live_peer_session_is_not_failed(self, db, installation):
        """At boot, most RUNNING rows belong to workers that never stopped.
        Failing them killed sessions a user was actively watching."""
        alive = await _running_session(db, installation, "c-alive")
        docker = FakeDocker(alive={"c-alive"})

        assert await reconcile_stale_sessions(db, docker) == 0
        assert alive.status == ContainerStatus.RUNNING

    async def test_a_session_whose_container_is_gone_is_failed(self, db, installation):
        dead = await _running_session(db, installation, "c-dead")
        docker = FakeDocker(alive=set())

        assert await reconcile_stale_sessions(db, docker) == 1
        assert dead.status == ContainerStatus.FAILED
        assert dead.completed_at is not None

    async def test_a_pending_session_that_never_started_is_failed(self, db, installation):
        """No container id means it never got that far, so nothing is running
        for it either way."""
        cs = ContainerSession(
            installation_id=installation.id,
            pr_number=2,
            repo_full_name="acme/repo",
            skill_name="challenge-me",
            status=ContainerStatus.PENDING,
        )
        db.add(cs)
        await db.flush()

        assert await reconcile_stale_sessions(db, FakeDocker()) == 1
        assert cs.status == ContainerStatus.FAILED

    async def test_the_live_and_the_dead_are_separated(self, db, installation):
        alive = await _running_session(db, installation, "c-alive")
        dead = await _running_session(db, installation, "c-dead")
        docker = FakeDocker(alive={"c-alive"})

        assert await reconcile_stale_sessions(db, docker) == 1
        assert alive.status == ContainerStatus.RUNNING
        assert dead.status == ContainerStatus.FAILED
