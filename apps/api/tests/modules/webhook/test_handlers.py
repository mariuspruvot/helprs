"""Tests for webhook handlers.

Tests the installation lifecycle handlers (created, deleted, suspended,
unsuspended). Pull-request session-creation handlers were removed as part
of the Claude Code container pivot (ADR-001).
"""

import pytest

from helprs.modules.installation.models import Installation
from helprs.modules.webhook import handlers
from tests.github_double import serving_github
from tests.modules.webhook.conftest import make_pull_request_payload


@pytest.fixture
async def test_installation(db_session):
    """Installation row matching the default webhook payload id."""
    installation = Installation(
        github_installation_id=12345678,
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
    db_session.add(installation)
    await db_session.flush()
    return installation


class TestHandleInstallationCreated:
    async def test_creates_installation(self, db_session):
        payload = {
            "action": "created",
            "installation": {
                "id": 99999999,
                "account": {"login": "neworg", "id": 88888, "type": "Organization"},
                "repository_selection": "all",
                "app_slug": "helprs",
                "target_type": "Organization",
                "permissions": {"pull_requests": "read"},
                "events": ["pull_request"],
                "suspended_at": None,
            },
            "sender": {"login": "admin-user", "id": 111},
        }
        await handlers.handle_installation_created(payload, db_session)


class TestHandleInstallationDeleted:
    async def test_deletes_existing_installation(self, db_session, test_installation):
        payload = {"installation": {"id": 12345678}}
        await handlers.handle_installation_deleted(payload, db_session)

    async def test_logs_warning_when_not_found(self, db_session):
        payload = {"installation": {"id": 99999999}}
        await handlers.handle_installation_deleted(payload, db_session)


class TestHandleInstallationSuspended:
    async def test_suspends_existing_installation(self, db_session, test_installation):
        payload = {"installation": {"id": 12345678}}
        await handlers.handle_installation_suspended(payload, db_session)

    async def test_logs_warning_when_not_found(self, db_session):
        payload = {"installation": {"id": 99999999}}
        await handlers.handle_installation_suspended(payload, db_session)


class TestHandleInstallationUnsuspended:
    async def test_unsuspends_existing_installation(self, db_session, test_installation):
        payload = {"installation": {"id": 12345678}}
        await handlers.handle_installation_unsuspended(payload, db_session)

    async def test_logs_warning_when_not_found(self, db_session):
        payload = {"installation": {"id": 99999999}}
        await handlers.handle_installation_unsuspended(payload, db_session)


class TestMalformedPayload:
    async def test_extract_installation_id_raises_on_missing_field(self):
        with pytest.raises(ValueError, match="missing installation.id"):
            handlers._extract_installation_id({})

    async def test_extract_installation_id_raises_on_none(self):
        with pytest.raises(ValueError, match="missing installation.id"):
            handlers._extract_installation_id({"installation": None})


class TestHandlePullRequestOpened:
    """Session creation, and the suppression labels that prevent it."""

    @pytest.fixture(autouse=True)
    def _signable_app_jwt(self, monkeypatch):
        """Signing needs a real RSA key; the mint request itself is served
        by the double."""
        monkeypatch.setattr(
            "helprs.modules.installation.service.create_app_jwt",
            lambda app_id, private_key: "signed.app.jwt",
        )

    async def _sessions_for(self, db_session, installation):
        from sqlalchemy import select

        from helprs.modules.container.models import ContainerSession

        result = await db_session.execute(
            select(ContainerSession).where(ContainerSession.installation_id == installation.id)
        )
        return list(result.scalars().all())

    async def test_creates_a_session_and_announces_it(self, db_session, test_installation):
        payload = make_pull_request_payload("opened")

        with serving_github() as github:
            await handlers.handle_pull_request_opened(payload, db_session)

        sessions = await self._sessions_for(db_session, test_installation)
        assert len(sessions) == 1
        assert sessions[0].pr_number == 42
        assert sessions[0].repo_full_name == "acme/repo"
        assert [r for r in github.requests if r.url.path.endswith("/comments")]

    async def test_suppression_label_prevents_the_session(self, db_session, test_installation):
        """Configuring labels used to have no effect at all: the setting was
        stored, exposed and edited in the UI, but never read here."""
        test_installation.suppression_labels = ["hotfix"]
        await db_session.flush()
        payload = make_pull_request_payload("opened", labels=["hotfix"])

        with serving_github() as github:
            await handlers.handle_pull_request_opened(payload, db_session)

        assert await self._sessions_for(db_session, test_installation) == []
        assert github.requests == []

    async def test_label_matching_ignores_case(self, db_session, test_installation):
        test_installation.suppression_labels = ["HotFix"]
        await db_session.flush()
        payload = make_pull_request_payload("opened", labels=["hotfix"])

        with serving_github():
            await handlers.handle_pull_request_opened(payload, db_session)

        assert await self._sessions_for(db_session, test_installation) == []

    async def test_unrelated_labels_do_not_suppress(self, db_session, test_installation):
        test_installation.suppression_labels = ["hotfix"]
        await db_session.flush()
        payload = make_pull_request_payload("opened", labels=["enhancement"])

        with serving_github():
            await handlers.handle_pull_request_opened(payload, db_session)

        assert len(await self._sessions_for(db_session, test_installation)) == 1

    async def test_no_configured_labels_never_suppresses(self, db_session, test_installation):
        payload = make_pull_request_payload("opened", labels=["hotfix", "urgent"])

        with serving_github():
            await handlers.handle_pull_request_opened(payload, db_session)

        assert len(await self._sessions_for(db_session, test_installation)) == 1

    async def test_unknown_installation_is_ignored(self, db_session):
        payload = make_pull_request_payload("opened")

        with serving_github() as github:
            await handlers.handle_pull_request_opened(payload, db_session)

        assert github.requests == []

    async def test_a_failing_comment_does_not_lose_the_session(self, db_session, test_installation):
        """The comment is best effort; the session must survive GitHub being down."""
        payload = make_pull_request_payload("opened")

        with serving_github(fail_comments=True):
            await handlers.handle_pull_request_opened(payload, db_session)

        assert len(await self._sessions_for(db_session, test_installation)) == 1
