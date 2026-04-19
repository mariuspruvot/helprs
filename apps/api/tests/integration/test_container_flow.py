"""Integration tests: webhook received -> container session created -> lifecycle managed -> results streamed.

These tests verify the chain of modules working together with Docker mocked out.
They use AsyncClient + ASGITransport against the real FastAPI app.
"""

import hashlib
import hmac
import os

# Set env vars BEFORE any app imports -- order matters for pydantic-settings.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-integration-tests")
os.environ.setdefault("FERNET_KEY", "VGhpcyBpcyBhIDMyIGJ5dGUga2V5IQ==")  # placeholder, overridden below
os.environ.setdefault("GITHUB_APP_ID", "123456")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("GITHUB_APP_PRIVATE_KEY", "")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")

from collections.abc import AsyncIterator

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.database import Base
from helprs.modules.container.models import ContainerSession, ContainerStatus
from helprs.modules.installation.models import BYOKConfig, Installation

# Generate a valid Fernet key for tests and set it in the environment.
_FERNET_KEY = Fernet.generate_key().decode()
os.environ["FERNET_KEY"] = _FERNET_KEY

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeDockerClient:
    """Test double implementing the DockerClient protocol."""

    def __init__(
        self,
        container_id: str = "integ-container-001",
        log_lines: list[str] | None = None,
    ):
        self._container_id = container_id
        self._log_lines = log_lines or ["output line 1\n", "output line 2\n", "done\n"]
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
        self.created.append({"image": image, "environment": environment, "volumes": volumes, "labels": labels})
        return self._container_id

    async def start_container(self, container_id: str) -> None:
        self.started.append(container_id)

    async def stop_container(self, container_id: str) -> None:
        self.stopped.append(container_id)

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        self.removed.append(container_id)

    async def container_logs(self, container_id: str, follow: bool = False) -> AsyncIterator[str]:
        for line in self._log_lines:
            yield line

    async def wait_container(self, container_id: str) -> int:
        return 0

    async def close(self) -> None:
        pass


# Singleton fake Docker client shared across a test run.
_fake_docker = FakeDockerClient()


def _get_fake_docker_client():
    """Return the shared fake Docker client instead of a real one."""
    return _fake_docker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_fake_docker():
    """Reset the fake Docker client state before each test."""
    _fake_docker.created.clear()
    _fake_docker.started.clear()
    _fake_docker.stopped.clear()
    _fake_docker.removed.clear()


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
    """Create a test installation in the DB."""
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
async def installation_with_byok(db: AsyncSession, installation: Installation) -> Installation:
    """Create a test installation with BYOK credentials configured."""
    from helprs.core.security import fernet_encrypt

    encrypted_key = fernet_encrypt("sk-ant-test-key-12345678", _FERNET_KEY)
    byok = BYOKConfig(
        installation_id=installation.id,
        encrypted_api_key=encrypted_key,
        key_status="valid",
        key_hint="...5678",
    )
    db.add(byok)
    await db.flush()
    return installation


@pytest.fixture
async def client(engine):
    """AsyncClient wired to the real FastAPI app with Docker patched out.

    Patches the container router's _get_docker_client to return the fake,
    and sets up the app state with a real DB session factory.
    """
    import helprs.modules.container.router as container_router_module
    from helprs.core.config import get_settings
    from helprs.main import create_app

    get_settings.cache_clear()

    app = create_app()

    # Patch the Docker client factory on the container router module.
    original_get_docker = container_router_module._get_docker_client
    container_router_module._get_docker_client = _get_fake_docker_client

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        # The app lifespan creates its own engine. We let it run via the
        # ASGITransport (which triggers lifespan events).
        yield ac

    container_router_module._get_docker_client = original_get_docker
    get_settings.cache_clear()


def _sign_payload(payload: bytes) -> str:
    """Compute the HMAC SHA-256 signature for a webhook payload."""
    sig = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={sig}"


# ---------------------------------------------------------------------------
# Tests: Full container session lifecycle (via service layer directly)
# ---------------------------------------------------------------------------


class TestContainerSessionLifecycle:
    """Test the complete session lifecycle through the service layer with a real DB."""

    async def test_full_container_session_lifecycle(
        self,
        db: AsyncSession,
        installation: Installation,
    ):
        """Create -> verify pending -> start -> verify running -> stop -> verify completed."""
        from helprs.modules.container.service import create_session, get_session, start_container, stop_container

        # 1. Create session
        cs = await create_session(
            db=db,
            installation_id=installation.id,
            pr_number=42,
            repo_full_name="test-org/my-repo",
            skill_name="challenge-me",
        )
        assert cs.status == ContainerStatus.PENDING
        assert cs.pr_number == 42
        assert cs.repo_full_name == "test-org/my-repo"
        assert cs.skill_name == "challenge-me"
        assert cs.container_id is None

        # 2. Verify session in DB
        found = await get_session(db, cs.id)
        assert found is not None
        assert found.id == cs.id
        assert found.installation_id == installation.id

        # 3. Start the container (with a temporary skill dir)
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            skills_path = Path(tmpdir)
            (skills_path / "challenge-me").mkdir()
            (skills_path / "challenge-me" / "prompt.md").write_text("test")

            cs = await start_container(
                db=db,
                session_id=cs.id,
                docker=_fake_docker,
                claude_oauth_token="test-oauth-token",
                github_token="gho_test",
                skills_base_path=skills_path,
            )

        assert cs.status == ContainerStatus.RUNNING
        assert cs.container_id == "integ-container-001"
        assert cs.started_at is not None

        # 4. Stop the container
        cs = await stop_container(db=db, session_id=cs.id, docker=_fake_docker)
        assert cs.status == ContainerStatus.COMPLETED
        assert cs.completed_at is not None

        # 5. Verify Docker interactions happened in order
        assert len(_fake_docker.created) == 1
        assert len(_fake_docker.started) == 1
        assert len(_fake_docker.stopped) == 1

    async def test_container_session_stream_sse(
        self,
        db: AsyncSession,
        installation: Installation,
    ):
        """Create a session in running state and verify SSE output format."""
        from helprs.modules.container.service import stream_output

        # Stream output from the fake Docker client
        events: list[str] = []
        async for event in stream_output(_fake_docker, "integ-container-001"):
            events.append(event)

        # Each line should be SSE-formatted
        assert len(events) == 3
        assert events[0] == "id: 1\ndata: output line 1\n\n"
        assert events[1] == "id: 2\ndata: output line 2\n\n"
        assert events[2] == "id: 3\ndata: done\n\n"


# ---------------------------------------------------------------------------
# Tests: Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """Test request validation via the Pydantic schemas."""

    def test_invalid_skill_name_rejected(self):
        """POST with an invalid skill name should fail validation."""
        from pydantic import ValidationError

        from helprs.modules.container.schemas import CreateSessionRequest

        with pytest.raises(ValidationError, match="skill_name"):
            CreateSessionRequest(
                installation_id=123456789,
                pr_number=1,
                repo_full_name="owner/repo",
                skill_name="invalid skill name with spaces!",
            )

    def test_invalid_repo_format_rejected(self):
        """POST with malformed repo_full_name should fail validation."""
        from pydantic import ValidationError

        from helprs.modules.container.schemas import CreateSessionRequest

        with pytest.raises(ValidationError, match="repo_full_name"):
            CreateSessionRequest(
                installation_id=123456789,
                pr_number=1,
                repo_full_name="not-a-valid-repo-format",
                skill_name="challenge-me",
            )

    def test_valid_request_accepted(self):
        """A well-formed request should pass validation."""
        from helprs.modules.container.schemas import CreateSessionRequest

        req = CreateSessionRequest(
            installation_id=123456789,
            pr_number=10,
            repo_full_name="owner/repo",
            skill_name="challenge-me",
        )
        assert req.pr_number == 10
        assert req.skill_name == "challenge-me"

    def test_negative_pr_number_rejected(self):
        """PR number must be positive."""
        from pydantic import ValidationError

        from helprs.modules.container.schemas import CreateSessionRequest

        with pytest.raises(ValidationError, match="pr_number"):
            CreateSessionRequest(
                installation_id=123456789,
                pr_number=-1,
                repo_full_name="owner/repo",
                skill_name="challenge-me",
            )

    def test_empty_owner_in_repo_rejected(self):
        """repo_full_name with empty owner segment should fail."""
        from pydantic import ValidationError

        from helprs.modules.container.schemas import CreateSessionRequest

        with pytest.raises(ValidationError, match="repo_full_name"):
            CreateSessionRequest(
                installation_id=123456789,
                pr_number=1,
                repo_full_name="/repo",
                skill_name="challenge-me",
            )


# ---------------------------------------------------------------------------
# Tests: Webhook -> container session chain
# ---------------------------------------------------------------------------


class TestWebhookToContainerSession:
    """Test the pull_request.opened webhook handler creating a container session."""

    async def test_pr_opened_creates_container_session(
        self,
        db: AsyncSession,
        installation: Installation,
    ):
        """Dispatching a pull_request.opened event should create a session in the DB."""
        from helprs.modules.webhook.dispatcher import dispatch_webhook

        payload = {
            "action": "opened",
            "installation": {"id": installation.github_installation_id},
            "pull_request": {
                "number": 99,
                "user": {"login": "dev-user"},
                "head": {"sha": "abc123"},
            },
            "repository": {
                "full_name": "test-org/my-repo",
            },
        }

        result = await dispatch_webhook("pull_request", "opened", payload, db)
        assert result.handled is True

        # Verify a ContainerSession was created in the DB
        stmt = select(ContainerSession).where(
            ContainerSession.installation_id == installation.id,
            ContainerSession.pr_number == 99,
        )
        row = await db.execute(stmt)
        cs = row.scalar_one_or_none()
        assert cs is not None
        assert cs.repo_full_name == "test-org/my-repo"
        assert cs.skill_name == "challenge-me"
        assert cs.status == ContainerStatus.PENDING

    async def test_pr_opened_missing_installation_is_noop(
        self,
        db: AsyncSession,
    ):
        """If the installation is not found in DB, the handler should log and return."""
        from helprs.modules.webhook.dispatcher import dispatch_webhook

        payload = {
            "action": "opened",
            "installation": {"id": 77777777},
            "pull_request": {
                "number": 1,
                "user": {"login": "dev-user"},
            },
            "repository": {
                "full_name": "unknown-org/repo",
            },
        }

        result = await dispatch_webhook("pull_request", "opened", payload, db)
        assert result.handled is True

        # No session should be created
        stmt = select(ContainerSession).where(ContainerSession.pr_number == 1)
        row = await db.execute(stmt)
        assert row.scalar_one_or_none() is None

    async def test_pr_opened_missing_pr_fields_is_noop(
        self,
        db: AsyncSession,
        installation: Installation,
    ):
        """If the payload is missing PR number or repo, handler returns without creating a session."""
        from helprs.modules.webhook.dispatcher import dispatch_webhook

        payload = {
            "action": "opened",
            "installation": {"id": installation.github_installation_id},
            "pull_request": {},
            "repository": {},
        }

        result = await dispatch_webhook("pull_request", "opened", payload, db)
        assert result.handled is True

        # No session should be created
        stmt = select(ContainerSession).where(ContainerSession.installation_id == installation.id)
        row = await db.execute(stmt)
        assert row.scalar_one_or_none() is None

    async def test_pr_opened_captures_correct_metadata(
        self,
        db: AsyncSession,
        installation: Installation,
    ):
        """Verify PR number, repo name, and skill assignment are captured correctly."""
        from helprs.modules.webhook.dispatcher import dispatch_webhook

        payload = {
            "action": "opened",
            "installation": {"id": installation.github_installation_id},
            "pull_request": {
                "number": 42,
                "user": {"login": "author"},
                "head": {"sha": "deadbeef"},
            },
            "repository": {
                "full_name": "test-org/backend-api",
            },
        }

        await dispatch_webhook("pull_request", "opened", payload, db)

        stmt = select(ContainerSession).where(
            ContainerSession.installation_id == installation.id,
            ContainerSession.pr_number == 42,
        )
        row = await db.execute(stmt)
        cs = row.scalar_one()
        assert cs.repo_full_name == "test-org/backend-api"
        assert cs.skill_name == "challenge-me"
        assert cs.status == ContainerStatus.PENDING
        assert cs.user_id is None  # No user association from webhook


# ---------------------------------------------------------------------------
# Tests: Dispatcher routing
# ---------------------------------------------------------------------------


class TestDispatcherRouting:
    """Verify the dispatcher correctly routes pull_request events."""

    async def test_unhandled_event_returns_ignored(
        self,
        db: AsyncSession,
    ):
        """An event type with no registered handler should return ignored."""
        from helprs.modules.webhook.dispatcher import dispatch_webhook

        result = await dispatch_webhook("unknown_event", "unknown_action", {}, db)
        assert result.handled is False

    async def test_pull_request_closed_is_unhandled(
        self,
        db: AsyncSession,
    ):
        """pull_request.closed has no handler registered, should be ignored."""
        from helprs.modules.webhook.dispatcher import dispatch_webhook

        payload = {
            "action": "closed",
            "installation": {"id": 12345},
            "pull_request": {"number": 1},
            "repository": {"full_name": "org/repo"},
        }
        result = await dispatch_webhook("pull_request", "closed", payload, db)
        assert result.handled is False
