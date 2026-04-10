"""Tests for pull_request webhook handlers.

Story 2.2 rewrites the Story 2.1 placeholders — the handlers now drive
session creation, suppression-label evaluation, and PR comment posting.
The DB writes and external-service calls that used to be TODO comments
are now real behavior and must be asserted on.
"""

import json
import logging
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from helprs.core.exceptions import ExternalServiceError, NotFoundError
from helprs.modules.comprehension.infrastructure.models import SessionModel
from helprs.modules.installation.models import Installation
from helprs.modules.webhook import handlers
from tests.modules.webhook.conftest import make_pull_request_payload


@pytest.fixture
async def test_installation(db_session):
    """Installation row matching the default ``make_pull_request_payload`` id."""
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


@pytest.fixture
def patched_github_calls(monkeypatch):
    """Patch mint_installation_token + post_pr_comment_with_retry at the
    webhook.handlers import site (standard "patch where used" rule).
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


class TestHandlePullRequestOpened:
    async def test_creates_sessions_and_posts_comment(self, db_session, test_installation, patched_github_calls):
        mint, post = patched_github_calls
        payload = make_pull_request_payload("opened")

        await handlers.handle_pull_request_opened(payload, db_session)

        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert len(rows) == 2
        assert {r.role for r in rows} == {"author", "reviewer"}

        mint.assert_awaited_once()
        post.assert_awaited_once()
        kwargs = post.await_args.kwargs
        assert kwargs["owner"] == "acme"
        assert kwargs["repo"] == "repo"
        assert kwargs["pr_number"] == 42
        assert kwargs["installation_token"] == "ghs_test_token"
        # Body contains both session links
        body = kwargs["body"]
        for row in rows:
            assert str(row.id) in body

    async def test_suppression_label_skips_session_and_comment(
        self, db_session, test_installation, patched_github_calls, caplog
    ):
        mint, post = patched_github_calls
        test_installation.suppression_labels = ["hotfix"]
        await db_session.flush()

        payload = make_pull_request_payload("opened", labels=["hotfix"])

        # Use caplog (not structlog.testing.capture_logs) — once the app
        # has configured structlog with cache_logger_on_first_use, cached
        # loggers route through stdlib logging and capture_logs() cannot
        # intercept them. This mirrors the pattern in test_router.py.
        caplog.set_level(logging.INFO)
        await handlers.handle_pull_request_opened(payload, db_session)

        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert rows == []
        mint.assert_not_awaited()
        post.assert_not_awaited()

        suppressed_events = []
        for record in caplog.records:
            try:
                entry = json.loads(record.getMessage())
            except json.JSONDecodeError:
                continue
            if entry.get("event") == "session_suppressed_by_label":
                suppressed_events.append(entry)

        assert suppressed_events, "expected a session_suppressed_by_label log entry"
        assert suppressed_events[0].get("label") == "hotfix"


class TestHandlePullRequestSynchronize:
    async def test_updates_existing_pair_without_posting_comment(
        self, db_session, test_installation, patched_github_calls
    ):
        mint, post = patched_github_calls

        # First: opened creates the pair
        await handlers.handle_pull_request_opened(make_pull_request_payload("opened", head_sha="old"), db_session)
        assert post.await_count == 1

        # Then: synchronize updates in place, no new comment
        await handlers.handle_pull_request_synchronize(
            make_pull_request_payload("synchronize", head_sha="new"), db_session
        )

        assert post.await_count == 1  # unchanged — no second comment
        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert len(rows) == 2
        assert all(r.pr_head_sha == "new" for r in rows)

    async def test_synchronize_without_prior_opened_creates_and_posts(
        self, db_session, test_installation, patched_github_calls
    ):
        """Race coverage: synchronize arrives first (AC #5)."""
        mint, post = patched_github_calls
        payload = make_pull_request_payload("synchronize")

        await handlers.handle_pull_request_synchronize(payload, db_session)

        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert len(rows) == 2
        post.assert_awaited_once()


class TestMalformedPayload:
    async def test_logs_warning_and_does_not_raise(self, db_session, test_installation, patched_github_calls, caplog):
        mint, post = patched_github_calls
        # Missing pull_request.head.sha
        payload = {
            "installation": {"id": 12345678},
            "pull_request": {
                "number": 42,
                "title": "Add foo",
                "diff_url": "https://github.com/acme/repo/pull/42.diff",
                "head": {},
                "labels": [],
            },
            "repository": {
                "full_name": "acme/repo",
                "name": "repo",
                "owner": {"login": "acme"},
            },
        }

        caplog.set_level(logging.WARNING)
        await handlers.handle_pull_request_opened(payload, db_session)

        malformed = []
        for record in caplog.records:
            try:
                entry = json.loads(record.getMessage())
            except json.JSONDecodeError:
                continue
            if entry.get("event") == "pull_request_event_malformed_payload":
                malformed.append(entry)
        assert malformed, "expected a pull_request_event_malformed_payload log entry"
        # No DB writes, no external calls
        rows = (await db_session.execute(select(SessionModel))).scalars().all()
        assert rows == []
        mint.assert_not_awaited()
        post.assert_not_awaited()


class TestInstallationNotFound:
    async def test_raises_not_found(self, db_session, patched_github_calls):
        # Note: no ``test_installation`` fixture — DB has no matching row
        payload = make_pull_request_payload("opened")

        with pytest.raises(NotFoundError):
            await handlers.handle_pull_request_opened(payload, db_session)


class TestCommentPostFailure:
    async def test_comment_post_failure_propagates(self, db_session, test_installation, monkeypatch):
        """If the PR comment post ultimately fails, the ``ExternalServiceError``
        propagates out of the handler so ``process_webhook_event`` can
        mark the ``webhook_events`` row ``failed``.

        Rollback correctness (sessions removed after the outer session
        exits) is covered end-to-end by
        ``test_router.py::TestSessionCreationAndComment::test_comment_post_failure_marks_event_failed``.
        """
        monkeypatch.setattr(
            "helprs.modules.webhook.handlers.mint_installation_token",
            AsyncMock(return_value="ghs_xxx"),
        )
        monkeypatch.setattr(
            "helprs.modules.webhook.handlers.post_pr_comment_with_retry",
            AsyncMock(side_effect=ExternalServiceError("boom")),
        )

        payload = make_pull_request_payload("opened")
        with pytest.raises(ExternalServiceError):
            await handlers.handle_pull_request_opened(payload, db_session)
