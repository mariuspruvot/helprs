"""Integration tests for webhook router.

Note on BackgroundTasks: httpx.ASGITransport DOES run BackgroundTasks after
the response is produced. Once ``await ac.post(...)`` returns, the background
task has already executed, so we can query the DB directly to assert the
final webhook_events row state — no sleeps, no polling.
"""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base
from helprs.main import create_app
from helprs.modules.comprehension.infrastructure.models import SessionModel
from helprs.modules.installation.models import Installation
from helprs.modules.webhook.models import WebhookEvent
from tests.modules.webhook.conftest import make_pull_request_payload, sign_payload

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"


@pytest.fixture
async def app_with_db():
    """Create app with a real test database.

    Pre-seeds an ``Installation`` row matching the default
    ``make_pull_request_payload`` (github_installation_id=12345678) so
    pull_request webhook tests exercise the Story-2.2 code path without
    each test having to bootstrap its own installation.
    """
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    application.state.session_factory = session_factory

    # Seed the installation row that the pull_request handlers rely on
    # (Story 2.2: the handler looks up the installation, raising
    # NotFoundError if absent).
    async with session_factory() as bootstrap:
        bootstrap.add(
            Installation(
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
        )
        await bootstrap.commit()

    yield application, session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _patch_github_calls(monkeypatch):
    """Patch mint_installation_token + post_pr_comment_with_retry so
    pull_request webhook tests never hit GitHub. Story 2.2.

    Scoped autouse — any test that doesn't exercise these calls is
    unaffected because the patched functions are only invoked via the
    pull_request handler path.
    """
    mint = AsyncMock(return_value="ghs_test_token")
    post = AsyncMock()
    monkeypatch.setattr(
        "helprs.modules.webhook.handlers.mint_installation_token",
        mint,
    )
    monkeypatch.setattr(
        "helprs.modules.webhook.handlers.post_pr_comment_with_retry",
        post,
    )
    return mint, post


@pytest.fixture
async def app_client(app_with_db):
    """Create a test client from app_with_db."""
    application, _ = app_with_db
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def session_factory(app_with_db):
    _, factory = app_with_db
    return factory


@pytest.fixture
def webhook_secret():
    get_settings.cache_clear()
    return get_settings().GITHUB_WEBHOOK_SECRET


def _delivery_id() -> str:
    return str(uuid.uuid4())


class TestWebhookRouter:
    async def test_installation_created_with_valid_hmac(
        self, app_client, webhook_secret, sample_installation_created_payload
    ):
        payload_bytes = json.dumps(sample_installation_created_payload).encode()
        signature = sign_payload(payload_bytes, webhook_secret)

        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "installation",
                "X-GitHub-Delivery": _delivery_id(),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_installation_deleted_with_valid_hmac(
        self, app_client, webhook_secret, sample_installation_deleted_payload
    ):
        # First create the installation
        created_payload = {
            **sample_installation_deleted_payload,
            "action": "created",
        }
        created_bytes = json.dumps(created_payload).encode()
        sig = sign_payload(created_bytes, webhook_secret)
        await app_client.post(
            "/api/v1/webhooks/github",
            content=created_bytes,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "installation",
                "X-GitHub-Delivery": _delivery_id(),
                "Content-Type": "application/json",
            },
        )

        # Now delete it
        payload_bytes = json.dumps(sample_installation_deleted_payload).encode()
        signature = sign_payload(payload_bytes, webhook_secret)

        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": signature,
                "X-GitHub-Event": "installation",
                "X-GitHub-Delivery": _delivery_id(),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200

    async def test_invalid_hmac_returns_401(self, app_client):
        payload_bytes = b'{"action": "created"}'
        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=payload_bytes,
            headers={
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "installation",
                "X-GitHub-Delivery": _delivery_id(),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    async def test_missing_signature_returns_401(self, app_client):
        payload_bytes = b'{"action": "created"}'
        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=payload_bytes,
            headers={
                "X-GitHub-Event": "installation",
                "X-GitHub-Delivery": _delivery_id(),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401


class TestWebhookPersistenceAndBackgroundDispatch:
    async def _post_pr(self, app_client, webhook_secret, *, action: str, delivery_id: str):
        payload = make_pull_request_payload(action)
        body = json.dumps(payload).encode()
        sig = sign_payload(body, webhook_secret)
        return await app_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": delivery_id,
                "Content-Type": "application/json",
            },
        )

    async def test_pull_request_opened_is_persisted_and_processed(self, app_client, webhook_secret, session_factory):
        delivery_id = _delivery_id()
        response = await self._post_pr(app_client, webhook_secret, action="opened", delivery_id=delivery_id)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "duplicate": False}

        async with session_factory() as s:
            result = await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))
            row = result.scalar_one()

        assert row.event_type == "pull_request"
        assert row.action == "opened"
        assert row.status == "processed"
        assert row.github_installation_id == 12345678
        assert row.processed_at is not None

    async def test_missing_delivery_id_returns_validation_error(self, app_client, webhook_secret):
        payload = make_pull_request_payload("opened")
        body = json.dumps(payload).encode()
        sig = sign_payload(body, webhook_secret)
        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 422

    async def test_duplicate_delivery_id_is_idempotent(self, app_client, webhook_secret, session_factory):
        delivery_id = _delivery_id()

        r1 = await self._post_pr(app_client, webhook_secret, action="opened", delivery_id=delivery_id)
        r2 = await self._post_pr(app_client, webhook_secret, action="opened", delivery_id=delivery_id)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json().get("duplicate") is True

        async with session_factory() as s:
            result = await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))
            rows = list(result.scalars().all())
        assert len(rows) == 1

    async def test_unhandled_pull_request_action_is_marked_ignored(self, app_client, webhook_secret, session_factory):
        delivery_id = _delivery_id()
        response = await self._post_pr(app_client, webhook_secret, action="closed", delivery_id=delivery_id)
        assert response.status_code == 200

        async with session_factory() as s:
            result = await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))
            row = result.scalar_one()

        assert row.status == "ignored"
        assert row.processed_at is not None

    async def test_unknown_event_type_is_marked_ignored(self, app_client, webhook_secret, session_factory):
        delivery_id = _delivery_id()
        payload = {"action": "opened", "repository": {"full_name": "a/b"}}
        body = json.dumps(payload).encode()
        sig = sign_payload(body, webhook_secret)
        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": delivery_id,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200

        async with session_factory() as s:
            result = await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))
            row = result.scalar_one()
        assert row.status == "ignored"

    async def test_non_dict_json_body_returns_validation_error(self, app_client, webhook_secret, session_factory):
        """Regression for: bare ``null`` / array / primitive body must not 500.

        Prior to the fix, ``payload.get("action")`` crashed with
        ``AttributeError`` and the row was never persisted.
        """
        for bad_body in (b"null", b"[]", b'"oops"', b"42"):
            sig = sign_payload(bad_body, webhook_secret)
            response = await app_client.post(
                "/api/v1/webhooks/github",
                content=bad_body,
                headers={
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": _delivery_id(),
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 422, f"bad body {bad_body!r} should 422"

        # No rows persisted from any of the invalid bodies.
        async with session_factory() as s:
            count = (await s.execute(select(WebhookEvent))).scalars().all()
        assert len(count) == 0

    async def test_whitespace_delivery_id_is_rejected(self, app_client, webhook_secret):
        """Whitespace-only ``X-GitHub-Delivery`` must be rejected like empty."""
        payload = make_pull_request_payload("opened")
        body = json.dumps(payload).encode()
        sig = sign_payload(body, webhook_secret)
        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "   ",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 422

    async def test_response_shape_includes_duplicate_key_on_happy_path(self, app_client, webhook_secret):
        """Regression for inconsistent response shape (duplicate key missing)."""
        delivery_id = _delivery_id()
        response = await self._post_pr(app_client, webhook_secret, action="opened", delivery_id=delivery_id)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "duplicate": False}


class TestWebhookAcCoverage:
    """Tests targeting ACs that previously had no direct coverage."""

    async def test_handler_exception_marks_row_failed(self, app_client, webhook_secret, session_factory):
        """AC #7: a raising handler must transition the row to ``failed``.

        The exception must NOT propagate to the HTTP response (200 is already
        returned before the background task runs) and the row must record
        ``error_message`` with ``retry_count == 1``.
        """
        from helprs.modules.webhook import dispatcher

        async def _boom(_payload, _session):
            raise RuntimeError("handler-exploded")

        delivery_id = _delivery_id()
        payload = make_pull_request_payload("opened")
        body = json.dumps(payload).encode()
        sig = sign_payload(body, webhook_secret)

        with patch.dict(dispatcher._HANDLERS, {("pull_request", "opened"): _boom}):
            response = await app_client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": delivery_id,
                    "Content-Type": "application/json",
                },
            )

        assert response.status_code == 200

        async with session_factory() as s:
            result = await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))
            row = result.scalar_one()

        assert row.status == "failed"
        assert row.error_message is not None
        assert "handler-exploded" in row.error_message
        assert row.retry_count == 1

    async def test_structlog_context_is_bound_with_required_fields(self, app_client, webhook_secret, caplog):
        """AC #5: log entries during webhook reception must carry the
        delivery_id / event_type / action / github_installation_id context.

        Uses pytest's ``caplog`` rather than ``structlog.testing.capture_logs``
        because the latter replaces the processor chain and drops the stdlib
        logging integration that the middleware/handlers actually use.
        """
        import logging

        caplog.set_level(logging.INFO)
        delivery_id = _delivery_id()
        payload = make_pull_request_payload("opened")
        body = json.dumps(payload).encode()
        sig = sign_payload(body, webhook_secret)

        response = await app_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": delivery_id,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200

        # Parse the structlog JSON messages from the stdlib log records and
        # assert at least one entry carries ALL four required context fields.
        matching = []
        for record in caplog.records:
            try:
                entry = json.loads(record.getMessage())
            except json.JSONDecodeError:
                continue
            if (
                entry.get("delivery_id") == delivery_id
                and entry.get("event_type") == "pull_request"
                and entry.get("action") == "opened"
                and entry.get("github_installation_id") == 12345678
            ):
                matching.append(entry)

        assert matching, (
            "No log entry carried the required AC #5 context fields. "
            f"Captured messages: {[r.getMessage() for r in caplog.records]}"
        )

    async def test_concurrent_claims_only_one_wins(self, session_factory):
        """P18: ``mark_processing`` is an atomic claim. Two concurrent workers
        must not both win the claim for the same event."""
        import asyncio

        from helprs.modules.webhook import repository

        async with session_factory() as s:
            event = await repository.create_event(
                s,
                delivery_id=f"claim-race-{uuid.uuid4()}",
                event_type="pull_request",
                action="opened",
                github_installation_id=1,
                payload={},
            )
            event_id = event.id

        async def _claim() -> bool:
            async with session_factory() as session:
                return await repository.mark_processing(session, event_id)

        results = await asyncio.gather(_claim(), _claim(), _claim())
        assert sum(1 for r in results if r) == 1, f"expected exactly one winner, got {results}"


class TestSessionCreationAndComment:
    """End-to-end coverage for Story 2.2 — the full opened → session pair →
    PR comment post flow exercised via the HTTP layer.

    These tests use the autouse ``_patch_github_calls`` fixture to stub
    both external calls; NFR1 real-network timing is covered manually.
    """

    async def _post_pr(
        self,
        app_client,
        webhook_secret,
        *,
        action: str = "opened",
        delivery_id: str,
        labels: list[str] | None = None,
        head_sha: str = "abc123",
    ):
        payload = make_pull_request_payload(action, labels=labels, head_sha=head_sha)
        body = json.dumps(payload).encode()
        sig = sign_payload(body, webhook_secret)
        return await app_client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": delivery_id,
                "Content-Type": "application/json",
            },
        )

    async def test_full_flow_creates_sessions_and_posts_comment(
        self, app_client, webhook_secret, session_factory, _patch_github_calls
    ):
        """Fast sanity check — with everything mocked, the full flow must
        complete well under 2 s. A blown budget here means a synchronous
        sleep has been introduced somewhere. Real-network p95 (10 s NFR1)
        is verified in manual QA.
        """
        import time

        mint, post = _patch_github_calls
        delivery_id = _delivery_id()

        start = time.perf_counter()
        response = await self._post_pr(app_client, webhook_secret, delivery_id=delivery_id)
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        assert elapsed < 2.0

        async with session_factory() as s:
            sessions = (await s.execute(select(SessionModel))).scalars().all()
            event = (await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))).scalar_one()

        assert len(sessions) == 2
        assert {r.role for r in sessions} == {"author", "reviewer"}
        assert event.status == "processed"

        mint.assert_awaited_once()
        post.assert_awaited_once()

    async def test_suppression_label_skips_sessions_and_comment(
        self, app_client, webhook_secret, session_factory, _patch_github_calls
    ):
        _, post = _patch_github_calls
        delivery_id = _delivery_id()
        response = await self._post_pr(app_client, webhook_secret, delivery_id=delivery_id, labels=["hotfix"])
        assert response.status_code == 200

        async with session_factory() as s:
            sessions = (await s.execute(select(SessionModel))).scalars().all()
            event = (await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))).scalar_one()

        assert sessions == []
        assert event.status == "processed"
        post.assert_not_awaited()

    async def test_synchronize_after_opened_updates_without_second_comment(
        self, app_client, webhook_secret, session_factory, _patch_github_calls
    ):
        _, post = _patch_github_calls

        d1 = _delivery_id()
        d2 = _delivery_id()
        await self._post_pr(app_client, webhook_secret, delivery_id=d1, head_sha="old")
        assert post.await_count == 1

        await self._post_pr(
            app_client,
            webhook_secret,
            action="synchronize",
            delivery_id=d2,
            head_sha="new",
        )
        assert post.await_count == 1  # no second comment on synchronize

        async with session_factory() as s:
            sessions = (await s.execute(select(SessionModel))).scalars().all()
            events = (
                (await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id.in_([d1, d2])))).scalars().all()
            )

        assert len(sessions) == 2
        assert all(r.pr_head_sha == "new" for r in sessions)
        assert len(events) == 2
        assert all(e.status == "processed" for e in events)

    async def test_comment_post_failure_marks_event_failed(
        self, app_client, webhook_secret, session_factory, monkeypatch
    ):
        from helprs.core.exceptions import ExternalServiceError

        monkeypatch.setattr(
            "helprs.modules.webhook.handlers.mint_installation_token",
            AsyncMock(return_value="ghs_xxx"),
        )
        monkeypatch.setattr(
            "helprs.modules.webhook.handlers.post_pr_comment_with_retry",
            AsyncMock(side_effect=ExternalServiceError("boom")),
        )

        delivery_id = _delivery_id()
        response = await self._post_pr(app_client, webhook_secret, delivery_id=delivery_id)
        assert response.status_code == 200

        async with session_factory() as s:
            event = (await s.execute(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id))).scalar_one()
            # Sessions were rolled back by the outer transaction boundary
            # when the handler raised (AC #6 interplay with Story 2.1's
            # mark_failed path).
            sessions = (await s.execute(select(SessionModel))).scalars().all()

        assert event.status == "failed"
        assert event.error_message is not None
        assert sessions == []
