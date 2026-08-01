"""End-to-end test of the credential rotation script.

Exercises the operation a self-hoster actually performs: deploy a new key
with the old one as a fallback, run the script, then confirm the old key can
be dropped without losing anything.
"""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base, clear_session_factory, set_session_factory
from helprs.core.security import fernet_decrypt, fernet_encrypt
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import BYOKConfig, Installation
from helprs.scripts.rotate_credentials import rotate_all

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"

OLD_KEY = Fernet.generate_key().decode()
NEW_KEY = Fernet.generate_key().decode()


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
async def factory(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    set_session_factory(session_factory)
    yield session_factory
    clear_session_factory()


@pytest.fixture
def rotating_settings(monkeypatch, engine):
    """Point the script at the test database, mid-rotation."""
    settings = get_settings().model_copy(
        update={
            "FERNET_KEY": type(get_settings().FERNET_KEY)(NEW_KEY),
            "FERNET_KEY_FALLBACKS": [type(get_settings().FERNET_KEY)(OLD_KEY)],
        }
    )
    monkeypatch.setattr("helprs.scripts.rotate_credentials.get_settings", lambda: settings)
    # A fresh engine per call, because the script owns and disposes the one it
    # builds. The schema lives in the database, not the engine, so the
    # fixture's tables are still there.
    monkeypatch.setattr(
        "helprs.scripts.rotate_credentials.create_engine",
        lambda: create_async_engine(TEST_DATABASE_URL, echo=False),
    )
    return settings


async def _seed(factory) -> tuple[GitHubUser, BYOKConfig]:
    """One of each credential kind, written under the OLD key."""
    async with factory() as session:
        user = GitHubUser(
            github_id=4242,
            github_login="rotator",
            email="rot@test.com",
            avatar_url=None,
            github_access_token_enc=fernet_encrypt("gho_original", [OLD_KEY]),
        )
        installation = Installation(
            github_installation_id=7777,
            account_login="acme",
            account_id=1,
            account_type="Organization",
            repository_selection="all",
            app_slug="helprs",
            target_type="Organization",
        )
        session.add_all([user, installation])
        await session.flush()

        config = BYOKConfig(
            installation_id=installation.id,
            encrypted_api_key=fernet_encrypt("sk-ant-oat-original", [OLD_KEY]),
            key_status="valid",
            key_hint="...inal",
        )
        session.add(config)
        await session.commit()
        return user, config


class TestRotateAll:
    async def test_every_credential_becomes_readable_by_the_new_key_alone(self, factory, rotating_settings):
        user, config = await _seed(factory)

        report = await rotate_all()

        assert report.failed == []
        assert report.rotated == 2

        async with factory() as session:
            refreshed_user = await session.get(GitHubUser, user.id)
            refreshed_config = await session.get(BYOKConfig, config.id)

        # The point of the exercise: FERNET_KEY_FALLBACKS can now be emptied.
        assert fernet_decrypt(refreshed_user.github_access_token_enc, [NEW_KEY]) == "gho_original"
        assert fernet_decrypt(refreshed_config.encrypted_api_key, [NEW_KEY]) == "sk-ant-oat-original"

    async def test_running_it_twice_changes_nothing(self, factory, rotating_settings):
        user, _ = await _seed(factory)

        await rotate_all()
        second = await rotate_all()

        assert second.failed == []
        async with factory() as session:
            refreshed = await session.get(GitHubUser, user.id)
        assert fernet_decrypt(refreshed.github_access_token_enc, [NEW_KEY]) == "gho_original"

    async def test_a_row_no_key_can_read_is_reported_not_overwritten(self, factory, rotating_settings):
        """A credential written under a key the operator forgot to list must
        be named in the report, and left intact so a later run can recover it
        once the missing key is supplied."""
        orphan_key = Fernet.generate_key().decode()
        async with factory() as session:
            user = GitHubUser(
                github_id=9999,
                github_login="orphan",
                email="orphan@test.com",
                avatar_url=None,
                github_access_token_enc=fernet_encrypt("gho_orphan", [orphan_key]),
            )
            session.add(user)
            await session.commit()
            original = user.github_access_token_enc

        report = await rotate_all()

        assert len(report.failed) == 1
        assert "orphan" in report.failed[0]

        async with factory() as session:
            refreshed = await session.get(GitHubUser, user.id)
        assert refreshed.github_access_token_enc == original
        assert fernet_decrypt(refreshed.github_access_token_enc, [orphan_key]) == "gho_orphan"
