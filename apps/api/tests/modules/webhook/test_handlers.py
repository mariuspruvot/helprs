"""Tests for webhook handlers.

Tests the installation lifecycle handlers (created, deleted, suspended,
unsuspended). Pull-request session-creation handlers were removed as part
of the Claude Code container pivot (ADR-001).
"""

import pytest

from helprs.modules.installation.models import Installation
from helprs.modules.webhook import handlers


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
