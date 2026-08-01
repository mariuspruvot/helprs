"""Tests for installation use cases: lifecycle, discovery, access control.

The GitHub boundary has its own tests (``test_github.py``); here the network
is served by ``GitHubDouble`` so these exercise orchestration and SQL.
"""

import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from helprs.core.exceptions import ForbiddenError, UnauthorizedError
from helprs.core.security import fernet_encrypt
from helprs.modules.container.models import ContainerSession, ContainerStatus
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import Installation
from helprs.modules.installation.schemas import InstallationPayload
from helprs.modules.installation.service import (
    create_installation,
    get_installation_by_github_id,
    get_installations_for_user,
    mint_installation_token,
    soft_delete_installation,
    suspend_installation,
    unsuspend_installation,
    verify_admin_permission,
    verify_installation_access,
    verify_session_access,
)
from tests.github_double import serving_github

WEBHOOK_PAYLOAD = {
    "installation": {
        "id": 12341234,
        "account": {"login": "acme", "id": 4242, "type": "Organization"},
        "repository_selection": "all",
        "app_slug": "helprs",
        "target_type": "Organization",
        "permissions": {"pull_requests": "read"},
        "events": ["pull_request"],
    }
}


async def _make_user_installation(db_session, *, account_id: int, github_installation_id: int = 5150) -> Installation:
    installation = Installation(
        github_installation_id=github_installation_id,
        account_login="octocat",
        account_id=account_id,
        account_type="User",
        repository_selection="all",
        app_slug="helprs",
        target_type="User",
    )
    db_session.add(installation)
    await db_session.flush()
    return installation


async def _make_other_user(db_session, settings) -> GitHubUser:
    """A second, real user row — session.user_id is a foreign key."""
    other = GitHubUser(
        github_id=76543210,
        github_login="someone-else",
        email="else@example.com",
        avatar_url=None,
        github_access_token_enc=fernet_encrypt("gho_other", settings.FERNET_KEY.get_secret_value()),
    )
    db_session.add(other)
    await db_session.flush()
    return other


async def _make_session(db_session, installation, *, owner_id: uuid.UUID | None) -> ContainerSession:
    container_session = ContainerSession(
        installation_id=installation.id,
        pr_number=1,
        repo_full_name="test-org/repo",
        skill_name="challenge-me",
        status=ContainerStatus.PENDING,
        user_id=owner_id,
    )
    db_session.add(container_session)
    await db_session.flush()
    return container_session


def _payload() -> InstallationPayload:
    return InstallationPayload.model_validate(WEBHOOK_PAYLOAD["installation"])


class TestCreateInstallation:
    async def test_creates_from_payload(self, db_session):
        installation = await create_installation(db_session, _payload())

        assert installation.github_installation_id == 12341234
        assert installation.account_login == "acme"
        assert installation.account_type == "Organization"

    async def test_duplicate_delivery_is_idempotent(self, db_session):
        first = await create_installation(db_session, _payload())
        second = await create_installation(db_session, _payload())

        assert first.id == second.id

    async def test_malformed_payload_is_rejected_at_the_boundary(self):
        """The use case takes a validated model, so a missing account is a
        ValidationError at parse time rather than a KeyError mid-use-case."""
        with pytest.raises(PydanticValidationError):
            InstallationPayload.model_validate({"id": 1})


class TestLifecycle:
    async def test_soft_delete_hides_the_row_from_lookups(self, db_session, test_installation):
        deleted = await soft_delete_installation(db_session, test_installation.github_installation_id)

        assert deleted is not None
        assert deleted.deleted_at is not None
        assert await get_installation_by_github_id(db_session, test_installation.github_installation_id) is None

    async def test_soft_delete_unknown_returns_none(self, db_session):
        assert await soft_delete_installation(db_session, 404404) is None

    async def test_suspend_then_unsuspend(self, db_session, test_installation):
        suspended = await suspend_installation(db_session, test_installation.github_installation_id)
        assert suspended is not None and suspended.suspended_at is not None

        resumed = await unsuspend_installation(db_session, test_installation.github_installation_id)
        assert resumed is not None and resumed.suspended_at is None

    async def test_lookup_finds_installation(self, db_session, test_installation):
        found = await get_installation_by_github_id(db_session, test_installation.github_installation_id)

        assert found is not None
        assert found.id == test_installation.id


class TestMintInstallationToken:
    async def test_returns_the_bare_token(self, settings, test_installation, monkeypatch):
        # Signing needs a real RSA key; the JWT itself is not what this covers.
        monkeypatch.setattr(
            "helprs.modules.installation.service.create_app_jwt",
            lambda app_id, private_key: "signed.app.jwt",
        )

        with serving_github(installation_token="ghs_minted") as github:
            token = await mint_installation_token(test_installation.github_installation_id, settings)

        assert token == "ghs_minted"
        assert github.requests[0].headers["Authorization"] == "Bearer signed.app.jwt"


class TestGetInstallationsForUser:
    async def test_user_owned_install_needs_no_github_call(self, db_session, test_user, settings):
        user, _ = test_user
        await _make_user_installation(db_session, account_id=user.github_id)

        # No Org install exists, so /user/orgs must be skipped entirely.
        with serving_github() as github:
            installations = await get_installations_for_user(db_session, user, settings)

        assert [i.account_type for i in installations] == ["User"]
        assert github.requests == []

    async def test_excludes_installs_owned_by_someone_else(self, db_session, test_user, settings):
        user, _ = test_user
        await _make_user_installation(db_session, account_id=user.github_id + 1)

        with serving_github():
            installations = await get_installations_for_user(db_session, user, settings)

        assert installations == []

    async def test_includes_org_install_when_member(self, db_session, test_user, test_installation, settings):
        user, _ = test_user

        with serving_github(user_orgs=["test-org"]):
            installations = await get_installations_for_user(db_session, user, settings)

        assert [i.id for i in installations] == [test_installation.id]

    async def test_org_login_match_is_case_insensitive(self, db_session, test_user, test_installation, settings):
        user, _ = test_user

        with serving_github(user_orgs=["TEST-ORG"]):
            installations = await get_installations_for_user(db_session, user, settings)

        assert [i.id for i in installations] == [test_installation.id]

    async def test_excludes_org_install_when_not_member(self, db_session, test_user, test_installation, settings):
        user, _ = test_user

        with serving_github(user_orgs=["some-other-org"]):
            installations = await get_installations_for_user(db_session, user, settings)

        assert installations == []

    async def test_excludes_soft_deleted_installs(self, db_session, test_user, test_installation, settings):
        user, _ = test_user
        await soft_delete_installation(db_session, test_installation.github_installation_id)

        with serving_github(user_orgs=["test-org"]):
            installations = await get_installations_for_user(db_session, user, settings)

        assert installations == []


class TestVerifyInstallationAccess:
    async def test_owner_of_user_install_passes(self, db_session, test_user, settings):
        user, _ = test_user
        installation = await _make_user_installation(db_session, account_id=user.github_id)

        assert await verify_installation_access(user, installation, settings) is True

    async def test_non_owner_of_user_install_is_forbidden(self, db_session, test_user, settings):
        user, _ = test_user
        installation = await _make_user_installation(db_session, account_id=user.github_id + 1)

        with pytest.raises(ForbiddenError, match="do not have access"):
            await verify_installation_access(user, installation, settings)

    async def test_org_member_passes(self, test_user, test_installation, settings):
        user, _ = test_user

        with serving_github(user_orgs=["test-org"]):
            assert await verify_installation_access(user, test_installation, settings) is True

    async def test_org_non_member_is_forbidden(self, test_user, test_installation, settings):
        user, _ = test_user

        with serving_github(user_orgs=["unrelated"]), pytest.raises(ForbiddenError):
            await verify_installation_access(user, test_installation, settings)

    async def test_corrupted_stored_token_is_unauthorized(self, test_user, test_installation, settings):
        user, _ = test_user
        user.github_access_token_enc = "not-valid-ciphertext"

        with pytest.raises(UnauthorizedError, match="corrupted"):
            await verify_installation_access(user, test_installation, settings)


class TestVerifyAdminPermission:
    async def test_org_admin_passes(self, test_user, test_installation, settings):
        user, _ = test_user

        with serving_github(org_role="admin", org_state="active"):
            assert await verify_admin_permission(user, test_installation, settings) is True

    async def test_org_member_is_forbidden(self, test_user, test_installation, settings):
        user, _ = test_user

        with serving_github(org_role="member"), pytest.raises(ForbiddenError, match="admin access"):
            await verify_admin_permission(user, test_installation, settings)

    async def test_pending_admin_is_forbidden(self, test_user, test_installation, settings):
        user, _ = test_user

        with serving_github(org_role="admin", org_state="pending"), pytest.raises(ForbiddenError):
            await verify_admin_permission(user, test_installation, settings)

    async def test_owner_of_user_install_passes(self, db_session, test_user, settings):
        user, _ = test_user
        installation = await _make_user_installation(db_session, account_id=user.github_id)

        assert await verify_admin_permission(user, installation, settings) is True

    async def test_non_owner_of_user_install_is_forbidden(self, db_session, test_user, settings):
        user, _ = test_user
        installation = await _make_user_installation(db_session, account_id=user.github_id + 1)

        with pytest.raises(ForbiddenError, match="admin access"):
            await verify_admin_permission(user, installation, settings)


class TestVerifySessionAccess:
    async def test_owner_passes_without_calling_github(self, db_session, test_user, test_installation, settings):
        user, _ = test_user
        container_session = await _make_session(db_session, test_installation, owner_id=user.id)

        with serving_github() as github:
            assert await verify_session_access(user, container_session, db_session, settings) is True

        assert github.requests == []

    async def test_org_member_can_open_another_members_session(
        self, db_session, test_user, test_installation, settings
    ):
        user, _ = test_user
        other = await _make_other_user(db_session, settings)
        container_session = await _make_session(db_session, test_installation, owner_id=other.id)

        with serving_github(user_orgs=["test-org"]):
            assert await verify_session_access(user, container_session, db_session, settings) is True

    async def test_non_member_is_forbidden(self, db_session, test_user, test_installation, settings):
        user, _ = test_user
        other = await _make_other_user(db_session, settings)
        container_session = await _make_session(db_session, test_installation, owner_id=other.id)

        with serving_github(user_orgs=["unrelated"]), pytest.raises(ForbiddenError):
            await verify_session_access(user, container_session, db_session, settings)

    async def test_deleted_installation_is_forbidden(self, db_session, test_user, test_installation, settings):
        user, _ = test_user
        other = await _make_other_user(db_session, settings)
        container_session = await _make_session(db_session, test_installation, owner_id=other.id)
        await soft_delete_installation(db_session, test_installation.github_installation_id)

        with pytest.raises(ForbiddenError, match="Installation not found"):
            await verify_session_access(user, container_session, db_session, settings)
