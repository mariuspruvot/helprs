"""Integration tests for ``POST /api/v1/sessions/{id}/answers`` (Story 3.4).

Same shape as ``test_sse_stream.py`` — uses ``AsyncClient`` +
``ASGITransport`` so no real server runs and no real Anthropic
traffic happens. The LLM provider is mocked via dependency override
on ``get_llm_provider``.

Also covers the GET stream pause/resume refactor: the resume case is
locked here rather than in ``test_sse_stream.py`` because the
``count_answers + 1`` starting number depends on the new ``answers``
table existing.
"""

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base, set_session_factory
from helprs.core.security import create_access_token, fernet_encrypt
from helprs.main import create_app
from helprs.modules.comprehension.infrastructure.models import AnswerModel, QuestionModel, SessionModel
from helprs.modules.comprehension.presentation.dependencies import get_llm_provider
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import BYOKConfig, Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"

_TEST_GITHUB_USER_ID = 9999
_TEST_GITHUB_INSTALLATION_ID = 11223344


@pytest.fixture
async def app_with_db(monkeypatch):
    """Story 3.4 fixture mirror of ``test_sse_stream.py::app_with_db``.

    Seeds an installation, BYOK, user, and a 3-question session
    (``total_questions=3``). Tests can pre-create questions via
    ``SqlAlchemySessionRepository.append_question`` to drive the POST
    endpoint deterministically.
    """
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    application.state.session_factory = session_factory
    set_session_factory(session_factory)

    settings = get_settings()

    async with session_factory() as bootstrap:
        installation = Installation(
            github_installation_id=_TEST_GITHUB_INSTALLATION_ID,
            account_login="acme34",
            account_id=66666,
            account_type="Organization",
            repository_selection="all",
            app_slug="helprs",
            target_type="Organization",
            permissions={"pull_requests": "write"},
            events=["pull_request"],
            suppression_labels=None,
        )
        bootstrap.add(installation)
        await bootstrap.flush()

        byok = BYOKConfig(
            installation_id=installation.id,
            encrypted_api_key=fernet_encrypt("sk-ant-fake-34", settings.FERNET_KEY),
            key_status="valid",
            validated_at=datetime.now(UTC),
            key_hint="...fake",
        )
        bootstrap.add(byok)

        user = GitHubUser(
            github_id=_TEST_GITHUB_USER_ID,
            github_login="answer_user",
            email="answer@example.com",
            avatar_url=None,
            github_access_token_enc=fernet_encrypt("gho_test_token", settings.FERNET_KEY),
        )
        bootstrap.add(user)
        await bootstrap.flush()

        author = SessionModel(
            installation_id=installation.id,
            github_installation_id=_TEST_GITHUB_INSTALLATION_ID,
            repo_full_name="acme/ansx",
            repo_owner="acme",
            repo_name="ansx",
            pr_number=11,
            pr_title="Improve bar",
            pr_head_sha="cafefeed",
            pr_diff_url="https://github.com/acme/ansx/pull/11.diff",
            role="author",
            status="pending",
            total_questions=3,
        )
        bootstrap.add(author)
        await bootstrap.commit()

        seeded = {
            "installation_id": installation.id,
            "user_id": user.id,
            "author_id": author.id,
        }

    yield application, session_factory, seeded

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
def _patch_external_calls(monkeypatch):
    """Patch GitHub access check + diff fetch for both sse + repo paths."""
    from unittest.mock import AsyncMock

    mint = AsyncMock(return_value="ghs_fake_token")
    access_list = AsyncMock(return_value=[])
    diff = AsyncMock(
        return_value=(
            "diff --git a/apps/api/foo.py b/apps/api/foo.py\n"
            "--- a/apps/api/foo.py\n"
            "+++ b/apps/api/foo.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-def foo(): pass\n"
            "+def foo(): return 42\n"
            "diff --git a/retry.ts b/retry.ts\n"
            "--- a/retry.ts\n"
            "+++ b/retry.ts\n"
            "@@ -1 +1 @@\n"
            "-export const retry = 1;\n"
            "+export const retry = 2;\n"
        )
    )

    monkeypatch.setattr(
        "helprs.modules.comprehension.application.handlers.mint_installation_token",
        mint,
    )
    monkeypatch.setattr(
        "helprs.modules.comprehension.application.handlers.get_installations_for_user",
        access_list,
    )
    monkeypatch.setattr(
        "helprs.modules.comprehension.presentation.sse.fetch_pr_diff",
        diff,
    )
    return mint, access_list, diff


def _bearer(user_id) -> dict:
    get_settings.cache_clear()
    settings = get_settings()
    token = create_access_token(
        {"sub": str(user_id), "github_login": "answer_user"},
        settings.SECRET_KEY,
    )
    return {"Authorization": f"Bearer {token}"}


def _parse_sse(body: bytes) -> list[tuple[str, dict]]:
    import json

    text = body.decode("utf-8")
    frames: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_name = None
        data_line = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data_line = line.removeprefix("data: ").strip()
        if event_name and data_line is not None:
            frames.append((event_name, json.loads(data_line)))
    return frames


def _override_llm(app, provider) -> None:
    app.dependency_overrides[get_llm_provider] = lambda: provider


class _ScriptedFeedbackLLM:
    """Fake LLM provider that yields a scripted feedback stream."""

    def __init__(self, feedback_text: str = "Good answer. See retry.ts:5 for context.") -> None:
        self.feedback_text = feedback_text
        self.api_keys_seen: list[str] = []

    async def stream_feedback(
        self,
        *,
        question_text: str,  # noqa: ARG002
        answer_text: str,  # noqa: ARG002
        pr_diff: str,  # noqa: ARG002
        role,  # noqa: ARG002
        api_key: str,
    ) -> AsyncIterator[str]:
        self.api_keys_seen.append(api_key)
        for ch in self.feedback_text:
            await asyncio.sleep(0)
            yield ch

    async def generate_feedback(self, **kwargs) -> str:
        return self.feedback_text

    # The endpoint also constructs a question agent on the GET stream
    # path, but we never call it from these tests — supply a stub
    # for safety so attribute lookups don't blow up if a test path
    # accidentally invokes it.
    async def stream_question(self, **kwargs) -> AsyncIterator[str]:
        if False:  # pragma: no cover
            yield ""

    async def generate_question(self, **kwargs) -> str:
        return ""


class _EmptyFeedbackLLM(_ScriptedFeedbackLLM):
    """Yields zero tokens — exercises the empty-feedback placeholder path."""

    async def stream_feedback(self, **kwargs) -> AsyncIterator[str]:  # noqa: ARG002
        if False:  # pragma: no cover
            yield ""


class _RaisingFeedbackLLM(_ScriptedFeedbackLLM):
    """Yields one token then raises — exercises the error frame path."""

    async def stream_feedback(self, **kwargs) -> AsyncIterator[str]:  # noqa: ARG002
        import httpx

        yield "Hel"
        raise httpx.TimeoutException("upstream timeout")


async def _seed_installation_and_question(
    session_factory,
    seeded,
    *,
    question_text: str = "What did you assume?",
):
    """Pre-create one question via the repository so the POST endpoint
    can resolve it. Also stashes the verbatim text in the in-memory
    registry so the POST handler can find it.
    """
    from helprs.modules.comprehension.domain.value_objects import Topic
    from helprs.modules.comprehension.infrastructure.repositories import (
        SqlAlchemySessionRepository,
    )
    from helprs.modules.comprehension.presentation.answer_pubsub import stash_question_text

    async with session_factory() as s:
        repo = SqlAlchemySessionRepository(s)
        question = await repo.append_question(
            session_id=seeded["author_id"],
            topic=Topic.ARCHITECTURE,
            text_hash=hashlib.sha256(question_text.encode()).hexdigest(),
        )
        await s.commit()

    stash_question_text(seeded["author_id"], question.id, question_text)
    return question


class TestSubmitAnswerHappyPath:
    async def test_streams_feedback_then_done(self, app_with_db, _patch_external_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        await _seed_installation_and_question(session_factory, seeded)

        scripted = _ScriptedFeedbackLLM()
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "Because the diff fixes a bug."},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        frames = _parse_sse(resp.content)
        events = [e for (e, _) in frames]
        assert events.count("feedback_token") >= 1
        assert events.count("feedback") == 1
        assert events.count("done") == 1
        assert events[-1] == "done"

        feedback_payload = next(d for (e, d) in frames if e == "feedback")
        assert feedback_payload["text"] == "Good answer. See retry.ts:5 for context."
        assert feedback_payload["score"] is None
        assert feedback_payload["gaps"] == []
        # Story 3.4 D2: code_refs wire field was deleted. Code-link
        # detection is done frontend-side from the rendered markdown.
        assert "code_refs" not in feedback_payload
        assert "answer_id" in feedback_payload

        # BYOK forwarded to the LLM.
        assert scripted.api_keys_seen == ["sk-ant-fake-34"]

        # Exactly one row persisted in ``answers`` with hash + latency, no text column.
        async with session_factory() as s:
            rows = list((await s.execute(select(AnswerModel))).scalars().all())
            # Pull the question row so we can bound the latency check
            # against the actual persisted timestamp (A5 from review).
            q_rows = list((await s.execute(select(QuestionModel))).scalars().all())
        assert len(rows) == 1
        assert rows[0].text_hash == hashlib.sha256(b"Because the diff fixes a bug.").hexdigest()
        assert not hasattr(rows[0], "text")
        # Story 3.4 A5 (code-review): bounded latency assertion —
        # latency_ms must match the real wall-clock between question
        # commit and answer receipt, within a slack to absorb test
        # execution jitter.
        assert len(q_rows) == 1
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        q_created_ms = int(q_rows[0].created_at.timestamp() * 1000)
        expected_ms = now_ms - q_created_ms
        # Generous slack because CI runners can stall under load.
        assert 0 <= rows[0].latency_ms <= expected_ms + 5000


class TestSubmitAnswerErrorPaths:
    async def test_404_when_session_unknown(self, app_with_db, _patch_external_calls):
        application, _, seeded = app_with_db
        _override_llm(application, _ScriptedFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{uuid.uuid4()}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "x"},
            )
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")

    async def test_403_when_user_has_no_access(self, app_with_db, _patch_external_calls):
        application, _, seeded = app_with_db
        _, access_list, _ = _patch_external_calls
        access_list.return_value = []  # explicit
        _override_llm(application, _ScriptedFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "x"},
            )
        assert resp.status_code == 403
        assert resp.headers["content-type"].startswith("application/json")

    async def test_404_when_question_number_unknown(self, app_with_db, _patch_external_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        _override_llm(application, _ScriptedFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            # No questions exist on this session yet — number=99 must 404.
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 99, "text": "x"},
            )
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["error"] == "question_not_found"

    async def test_post_q1_succeeds_when_db_has_unanswered_q1_q2_q3(self, app_with_db, _patch_external_calls):
        """Story 3.4 kick-back regression (2026-04-11 BLOCKER #2).

        Before the fix, the *frontend* sent ``question_number=3`` (the
        most recently rendered question) for a session whose DB held
        Q1, Q2, Q3 with zero answers — the result of the BLOCKER #1
        SSE-reconnect bug. The backend's in-order check correctly
        rejected the out-of-order POST as 409 ``answer_out_of_order``,
        but the frontend collapsed it into "already answered". This
        test locks the OPPOSITE invariant: when an in-order POST for
        Q1 lands on the same dirty DB state, the backend MUST accept
        it (200 SSE response, answer persisted) — proving that the
        in-order enforcement keys off ``count_answers + 1`` and not
        ``max(question.number)``.
        """
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )
        from helprs.modules.comprehension.presentation.answer_pubsub import (
            stash_question_text,
        )

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        # Pre-seed three unanswered questions, mimicking the dirty
        # state from manual QA (3 questions committed in 3 separate
        # SSE connections, no answer ever submitted).
        q1_text = "Q1 about foo.py?"
        q2_text = "Q2 about bar.ts?"
        q3_text = "Q3 about edge cases?"
        async with session_factory() as s:
            repo = SqlAlchemySessionRepository(s)
            q1 = await repo.append_question(
                session_id=seeded["author_id"],
                topic=Topic.ARCHITECTURE,
                text_hash=hashlib.sha256(q1_text.encode()).hexdigest(),
            )
            await repo.append_question(
                session_id=seeded["author_id"],
                topic=Topic.ARCHITECTURE,
                text_hash=hashlib.sha256(q2_text.encode()).hexdigest(),
            )
            await repo.append_question(
                session_id=seeded["author_id"],
                topic=Topic.ARCHITECTURE,
                text_hash=hashlib.sha256(q3_text.encode()).hexdigest(),
            )
            await s.commit()
        # Stash texts so the POST handler's question-text lookup
        # succeeds — same way the GET stream's stash path would have
        # primed the registry on a real run.
        stash_question_text(seeded["author_id"], q1.id, q1_text)

        _override_llm(application, _ScriptedFeedbackLLM("Good answer for Q1."))

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "I assumed foo would be deterministic."},
            )

        # CRITICAL: must NOT be 409. The backend's in-order check
        # uses ``count_answers + 1`` (which is 1 here, since the
        # answers table is empty), so Q1 is the expected next answer
        # even though the DB max(question.number) is 3.
        assert resp.status_code == 200, (
            f"expected 200 (in-order POST for Q1 with 0 answers), got {resp.status_code}: {resp.text[:200]}"
        )
        assert resp.headers["content-type"].startswith("text/event-stream")

        # Sanity-check that the SSE body really contains a feedback
        # frame, not just an error frame masquerading as 200.
        frames = _parse_sse(resp.content)
        events = [e for (e, _) in frames]
        assert "feedback" in events
        assert events[-1] == "done"

        # Exactly one row in answers, attached to Q1's id.
        async with session_factory() as s:
            rows = list((await s.execute(select(AnswerModel))).scalars().all())
        assert len(rows) == 1
        assert rows[0].question_id == q1.id

    async def test_post_q3_when_no_answers_returns_out_of_order_not_already_submitted(
        self, app_with_db, _patch_external_calls
    ):
        """Companion to the test above: a client that POSTs the WRONG
        question number (3 instead of 1) must get the
        ``answer_out_of_order`` error code, not
        ``answer_already_submitted``. The frontend's 2026-04-11 patch
        relies on this discrimination to show the correct banner.
        """
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )
        from helprs.modules.comprehension.presentation.answer_pubsub import (
            stash_question_text,
        )

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        async with session_factory() as s:
            repo = SqlAlchemySessionRepository(s)
            q1 = await repo.append_question(
                session_id=seeded["author_id"], topic=Topic.ARCHITECTURE, text_hash="a" * 64
            )
            await repo.append_question(session_id=seeded["author_id"], topic=Topic.ARCHITECTURE, text_hash="b" * 64)
            q3 = await repo.append_question(
                session_id=seeded["author_id"], topic=Topic.ARCHITECTURE, text_hash="c" * 64
            )
            await s.commit()
        stash_question_text(seeded["author_id"], q1.id, "Q1 text")
        stash_question_text(seeded["author_id"], q3.id, "Q3 text")

        _override_llm(application, _ScriptedFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 3, "text": "out of order"},
            )

        assert resp.status_code == 409
        body = resp.json()
        assert body["detail"]["error"] == "answer_out_of_order"
        assert body["detail"]["expected_number"] == 1
        # And critically, the error code is NOT collapsed into
        # ``answer_already_submitted`` — that was the misleading
        # frontend message reported in the kick-back.
        assert body["detail"]["error"] != "answer_already_submitted"

    async def test_409_on_sequential_double_submit_is_out_of_order(self, app_with_db, _patch_external_calls):
        """Story 3.4 P4 (code-review E9): a client that submits the
        same ``question_number`` twice sequentially is now rejected
        by the in-order check (409 ``answer_out_of_order``) BEFORE
        reaching the unique-constraint path. The unique-constraint
        path still exists for concurrent races, but that code path
        is not exercised here.
        """
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        await _seed_installation_and_question(session_factory, seeded)
        _override_llm(application, _ScriptedFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            first = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "first answer"},
            )
            assert first.status_code == 200
            second = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "second answer"},
            )
        assert second.status_code == 409
        body = second.json()
        assert body["detail"]["error"] == "answer_out_of_order"
        assert body["detail"]["expected_number"] == 2

    async def test_422_on_empty_text(self, app_with_db, _patch_external_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        await _seed_installation_and_question(session_factory, seeded)
        _override_llm(application, _ScriptedFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": ""},
            )
        assert resp.status_code == 422

    async def test_422_on_text_too_long(self, app_with_db, _patch_external_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        await _seed_installation_and_question(session_factory, seeded)
        _override_llm(application, _ScriptedFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "x" * 8001},
            )
        assert resp.status_code == 422


class TestSubmitAnswerEdgeCases:
    async def test_llm_failure_emits_error_frame(self, app_with_db, _patch_external_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        await _seed_installation_and_question(session_factory, seeded)
        _override_llm(application, _RaisingFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "an answer"},
            )
        assert resp.status_code == 200
        frames = _parse_sse(resp.content)
        events = [e for (e, _) in frames]
        # Last frame is an `error` frame; `feedback`/`done` may or may
        # not have happened depending on where the exception fired.
        assert events[-1] == "error"
        err_payload = frames[-1][1]
        # P18 lock — assert keys, not class names.
        assert set(err_payload.keys()) >= {"error", "message", "retryable"}

        # Answer row was still committed (it lives BEFORE the stream).
        async with session_factory() as s:
            count = (await s.execute(select(func.count()).select_from(AnswerModel))).scalar_one()
        assert count == 1

    async def test_empty_feedback_emits_skipped_placeholder(self, app_with_db, _patch_external_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        await _seed_installation_and_question(session_factory, seeded)
        _override_llm(application, _EmptyFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "an answer"},
            )
        assert resp.status_code == 200
        frames = _parse_sse(resp.content)
        feedback_payloads = [d for (e, d) in frames if e == "feedback"]
        assert len(feedback_payloads) == 1
        assert "Skipped a question" in feedback_payloads[0]["text"]
        # D2: code_refs field was deleted from the wire.
        assert "code_refs" not in feedback_payloads[0]

        # Answer is still in the DB regardless.
        async with session_factory() as s:
            count = (await s.execute(select(func.count()).select_from(AnswerModel))).scalar_one()
        assert count == 1

    async def test_question_text_unavailable_after_restart(self, app_with_db, _patch_external_calls):
        """If the in-memory registry was cleared (server restart), the
        POST handler must return 422 with the documented error code.
        """
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )
        from helprs.modules.comprehension.presentation.answer_pubsub import reset_answer_pubsub

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        # Create the question WITHOUT stashing the text in the registry.
        async with session_factory() as s:
            repo = SqlAlchemySessionRepository(s)
            await repo.append_question(
                session_id=seeded["author_id"],
                topic=Topic.ARCHITECTURE,
                text_hash="a" * 64,
            )
            await s.commit()
        # Defensive: clear the registry so the lookup fails.
        reset_answer_pubsub()
        _override_llm(application, _ScriptedFeedbackLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/sessions/{seeded['author_id']}/answers",
                headers=_bearer(seeded["user_id"]),
                json={"question_number": 1, "text": "x"},
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["error"] == "question_text_unavailable_after_restart"
        # The request-scoped DB session rolls back on the
        # DomainValidationError raised AFTER append_answer's flush, so
        # the answer row is NOT persisted. Verifies the unit-of-work
        # correctness: a 422 leaves the DB clean, the user can retry
        # after the GET stream re-generates the question.
        async with session_factory() as s:
            count = (await s.execute(select(func.count()).select_from(AnswerModel))).scalar_one()
        assert count == 0


class TestPauseLoopResume:
    """Story 3.4 / Task 8.5: GET stream pause/resume integration.

    After the D1 polling rewrite + D4 last-question fix, these tests
    exercise the actual ``count_answers`` polling loop. They do NOT
    use the ``_skip_answer_polling`` monkeypatch so the real pause
    behaviour is verified.
    """

    async def test_resume_all_answered_emits_done_without_new_questions(self, app_with_db, _patch_external_calls):
        """All 3 questions already answered → stream emits no new
        ``question`` frames and closes with ``done`` immediately.
        Proves the resume path reads ``count_answers`` and skips the
        generation loop entirely when the session is fully answered.
        """
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        async with session_factory() as s:
            repo = SqlAlchemySessionRepository(s)
            q1 = await repo.append_question(
                session_id=seeded["author_id"], topic=Topic.ARCHITECTURE, text_hash="a" * 64
            )
            q2 = await repo.append_question(
                session_id=seeded["author_id"], topic=Topic.ARCHITECTURE, text_hash="b" * 64
            )
            q3 = await repo.append_question(
                session_id=seeded["author_id"], topic=Topic.ARCHITECTURE, text_hash="c" * 64
            )
            await repo.append_answer(question_id=q1.id, text_hash="1" * 64, latency_ms=10)
            await repo.append_answer(question_id=q2.id, text_hash="2" * 64, latency_ms=20)
            await repo.append_answer(question_id=q3.id, text_hash="3" * 64, latency_ms=30)
            await s.commit()

        # No LLM tokens should be drawn — override with a provider that
        # explodes if asked to stream, to prove generation was skipped.
        from .test_sse_stream import _ScriptedLLM

        scripted = _ScriptedLLM([])
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 200
        frames = _parse_sse(resp.content)
        question_frames = [d for (e, d) in frames if e == "question"]
        assert len(question_frames) == 0

        done_frames = [d for (e, d) in frames if e == "done"]
        assert len(done_frames) == 1
        assert done_frames[0]["question_count"] == 3


class TestGetStreamAdvancesOnAnswer:
    """Story 3.4 AC#15 Test 1 + D1 + D4 (code-review decisions).

    End-to-end: opening a GET stream, receiving one question frame,
    POSTing an answer, then observing the GET stream advance to the
    next question via the polling pause-loop. This is the test the
    Auditor flagged as missing — it exercises the *real*
    ``_wait_for_answer_count`` path with real POST traffic, rather
    than relying on the ``_skip_answer_polling`` monkeypatch.
    """

    async def test_post_answer_wakes_paused_get_stream(self, app_with_db, _patch_external_calls, monkeypatch):
        import asyncio

        # Speed up the pause-loop's polling interval so the test
        # doesn't wait half a second per iteration.
        from helprs.modules.comprehension.presentation import sse as sse_module

        monkeypatch.setattr(sse_module, "_ANSWER_POLL_INTERVAL_SECONDS", 0.02)

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        # Configure the session for 2 questions so the test is short.
        async with session_factory() as s:
            stmt = select(SessionModel).where(SessionModel.id == seeded["author_id"])
            sess = (await s.execute(stmt)).scalar_one()
            sess.total_questions = 2
            await s.commit()

        # Script a two-question LLM + a feedback LLM via a hybrid.
        from .test_sse_stream import _ScriptedLLM

        class _HybridLLM:
            def __init__(self):
                self._questions = _ScriptedLLM(["Q1 text?", "Q2 text?"])
                self._feedback = _ScriptedFeedbackLLM("Good answer.")

            def stream_question(self, **kwargs):
                return self._questions.stream_question(**kwargs)

            def stream_feedback(self, **kwargs):
                return self._feedback.stream_feedback(**kwargs)

        _override_llm(application, _HybridLLM())

        async def drive_get_stream() -> list:
            async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
                resp = await ac.get(
                    f"/api/v1/sessions/{seeded['author_id']}/stream",
                    headers=_bearer(seeded["user_id"]),
                )
            return _parse_sse(resp.content)

        async def post_answer_after_first_question(stream_task: asyncio.Task) -> None:
            # Poll the DB for the first question to land, then POST.
            from helprs.modules.comprehension.infrastructure.models import QuestionModel

            for _ in range(200):  # ~4 s worst case at 20 ms
                async with session_factory() as s:
                    count = (
                        await s.execute(
                            select(func.count())
                            .select_from(QuestionModel)
                            .where(QuestionModel.session_id == seeded["author_id"])
                        )
                    ).scalar_one()
                if count >= 1:
                    break
                await asyncio.sleep(0.02)
            async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/sessions/{seeded['author_id']}/answers",
                    headers=_bearer(seeded["user_id"]),
                    json={"question_number": 1, "text": "my answer to Q1"},
                )
            assert resp.status_code == 200
            # Then POST for Q2 after it lands.
            for _ in range(200):
                async with session_factory() as s:
                    count = (
                        await s.execute(
                            select(func.count())
                            .select_from(QuestionModel)
                            .where(QuestionModel.session_id == seeded["author_id"])
                        )
                    ).scalar_one()
                if count >= 2:
                    break
                await asyncio.sleep(0.02)
            async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/sessions/{seeded['author_id']}/answers",
                    headers=_bearer(seeded["user_id"]),
                    json={"question_number": 2, "text": "my answer to Q2"},
                )
            assert resp.status_code == 200

        stream_task = asyncio.create_task(drive_get_stream())
        poster_task = asyncio.create_task(post_answer_after_first_question(stream_task))

        frames = await asyncio.wait_for(stream_task, timeout=30.0)
        await asyncio.wait_for(poster_task, timeout=5.0)

        question_frames = [d for (e, d) in frames if e == "question"]
        done_frames = [d for (e, d) in frames if e == "done"]
        assert len(question_frames) == 2
        assert question_frames[0]["number"] == 1
        assert question_frames[1]["number"] == 2
        assert len(done_frames) == 1

        async with session_factory() as s:
            answer_count = (await s.execute(select(func.count()).select_from(AnswerModel))).scalar_one()
        assert answer_count == 2


class TestPauseLoopGatesOnFeedbackCommitted:
    """Story 3.4 v1.3.0 — BLOCKER #4 regression tests.

    Second manual QA pass (2026-04-11) showed the frontend rendered
    ``Q / A / Q_next / F`` instead of ``Q / A / F / Q_next`` after
    answering a question. Root cause: the GET pause-loop's
    ``_wait_for_answer_count`` only polled ``count_answers`` — which
    increments as soon as the POST /answers endpoint exits its DB
    context, several seconds BEFORE the feedback stream completes.
    Q_next began streaming while F_current was still on the wire.

    The fix (v1.3.0) introduced an in-process ``feedback_committed``
    flag in ``answer_pubsub`` that the POST sets AFTER yielding the
    ``feedback`` frame, and made ``_wait_for_answer_count`` gate on
    BOTH conditions. These tests lock that behaviour:

    (a) ``_wait_for_answer_count`` does NOT return on the DB
        condition alone — the flag must also be set.
    (b) End-to-end: while the POST is mid-feedback-stream (answer
        persisted, feedback not yet yielded), the concurrent GET
        stream is blocked on the first question frame and has NOT
        yet emitted Q_next.
    """

    async def test_wait_for_answer_count_blocks_until_feedback_committed(
        self, app_with_db, _patch_external_calls, monkeypatch
    ):
        """Unit-ish: the helper must not return on count alone."""
        from unittest.mock import AsyncMock

        from helprs.modules.comprehension.presentation import sse as sse_module
        from helprs.modules.comprehension.presentation.answer_pubsub import (
            mark_feedback_committed,
            reset_answer_pubsub,
        )

        _, _session_factory, seeded = app_with_db
        session_id = seeded["author_id"]

        reset_answer_pubsub()

        # Tight poll interval so the test finishes fast.
        monkeypatch.setattr(sse_module, "_ANSWER_POLL_INTERVAL_SECONDS", 0.01)

        # Pre-seed one answer so ``count_answers`` = 1 >= target on
        # the very first poll iteration. Without the BLOCKER #4 fix
        # the helper would return immediately. With the fix, it must
        # continue looping until ``mark_feedback_committed`` fires.
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )

        _, session_factory_local, _ = app_with_db
        async with session_factory_local() as s:
            repo = SqlAlchemySessionRepository(s)
            q1 = await repo.append_question(session_id=session_id, topic=Topic.ARCHITECTURE, text_hash="a" * 64)
            await repo.append_answer(question_id=q1.id, text_hash="1" * 64, latency_ms=10)
            await s.commit()

        # Fake Request that is never disconnected.
        fake_request = type("R", (), {})()
        fake_request.is_disconnected = AsyncMock(return_value=False)

        async def call_wait() -> None:
            await sse_module._wait_for_answer_count(
                session_id=session_id,
                target=1,
                request=fake_request,
            )

        wait_task = asyncio.create_task(call_wait())

        # Give the pause-loop several poll intervals to confirm it
        # does NOT return purely on the DB condition.
        await asyncio.sleep(0.1)
        assert not wait_task.done(), "pause-loop returned on count_answers alone — BLOCKER #4 regression"

        # Fire the feedback-committed signal. Within one poll interval
        # the helper should return cleanly.
        mark_feedback_committed(session_id, 1)

        await asyncio.wait_for(wait_task, timeout=1.0)
        assert wait_task.done()
        assert wait_task.exception() is None

    async def test_get_stream_waits_for_feedback_before_advancing(
        self, app_with_db, _patch_external_calls, monkeypatch
    ):
        """End-to-end: the GET pause-loop must not emit Q2 until the
        POST /answers feedback stream has fully yielded F1.

        Uses a slow-feedback LLM whose ``stream_feedback`` blocks on an
        ``asyncio.Event`` controlled by the test. While that event is
        unset, the POST generator is stuck mid-``feedback_token``, the
        answer row is already committed (so ``count_answers == 1``),
        and the GET pause-loop MUST NOT advance. Once the event fires,
        the feedback stream completes, ``mark_feedback_committed`` runs,
        and the GET pause-loop unblocks → Q2 emits.

        **Race observation (v1.3.0 review P3 hardening):** the earlier
        draft of this test observed the race via a ``q_count < 2``
        check after an ``await asyncio.sleep(0.2)`` window, which could
        pass on the buggy version in CI if Q2's DB insert happened to
        take longer than 200 ms. We now monkeypatch
        ``SqlAlchemySessionRepository.append_question`` with a spy that
        records ``time.monotonic()`` on each invocation, and capture a
        ``feedback_gate_released_at`` timestamp right before calling
        ``feedback_gate.set()``. The assertion is deterministic:
        ``append_question`` for Q2 MUST happen strictly after the gate
        release — the pause-loop cannot have advanced any earlier.
        """
        import time as _time

        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )
        from helprs.modules.comprehension.presentation import sse as sse_module

        monkeypatch.setattr(sse_module, "_ANSWER_POLL_INTERVAL_SECONDS", 0.02)

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_external_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        async with session_factory() as s:
            stmt = select(SessionModel).where(SessionModel.id == seeded["author_id"])
            sess = (await s.execute(stmt)).scalar_one()
            sess.total_questions = 2
            await s.commit()

        from .test_sse_stream import _ScriptedLLM

        feedback_gate = asyncio.Event()
        # Timestamp captured right before feedback_gate.set() — used as
        # the reference point for "Q2's append MUST happen after this".
        feedback_gate_released_at: list[float] = []
        # Timestamps for each append_question call, in invocation order.
        # On the correct code path there should be two entries; the
        # SECOND one (for Q2) must be > feedback_gate_released_at[0].
        append_question_timestamps: list[float] = []

        _original_append_question = SqlAlchemySessionRepository.append_question

        async def _spy_append_question(self, **kwargs):  # type: ignore[no-untyped-def]
            result = await _original_append_question(self, **kwargs)
            append_question_timestamps.append(_time.monotonic())
            return result

        monkeypatch.setattr(
            SqlAlchemySessionRepository,
            "append_question",
            _spy_append_question,
        )

        class _GatedFeedbackLLM:
            """First call to ``stream_feedback`` blocks on the gate,
            second call streams normally. Lets the test arrange a race
            window around F1 only.
            """

            def __init__(self):
                self._questions = _ScriptedLLM(["Q1 text?", "Q2 text?"])
                self._feedback_calls = 0

            def stream_question(self, **kwargs):
                return self._questions.stream_question(**kwargs)

            async def stream_feedback(self, **kwargs):  # noqa: ARG002
                self._feedback_calls += 1
                if self._feedback_calls == 1:
                    yield "partial "
                    await feedback_gate.wait()
                    yield "feedback."
                else:
                    yield "Good answer to Q2."

            async def generate_feedback(self, **kwargs) -> str:  # noqa: ARG002
                return ""

            async def generate_question(self, **kwargs) -> str:  # noqa: ARG002
                return ""

        _override_llm(application, _GatedFeedbackLLM())

        async def drive_get_stream() -> list:
            async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
                resp = await ac.get(
                    f"/api/v1/sessions/{seeded['author_id']}/stream",
                    headers=_bearer(seeded["user_id"]),
                )
            return _parse_sse(resp.content)

        async def post_answers_with_race_observation() -> None:
            # Wait for Q1 to land in the DB so the GET stream has
            # committed it and is sitting in the pause-loop.
            for _ in range(200):
                async with session_factory() as s:
                    count = (
                        await s.execute(
                            select(func.count())
                            .select_from(QuestionModel)
                            .where(QuestionModel.session_id == seeded["author_id"])
                        )
                    ).scalar_one()
                if count >= 1:
                    break
                await asyncio.sleep(0.01)

            async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
                # POST Q1 — first feedback call is gated. ``ac.post``
                # blocks until the full response body is read; we
                # spawn it so we can observe the race window.
                post_task_q1 = asyncio.create_task(
                    ac.post(
                        f"/api/v1/sessions/{seeded['author_id']}/answers",
                        headers=_bearer(seeded["user_id"]),
                        json={"question_number": 1, "text": "my answer to Q1"},
                    )
                )

                # Wait until the answer row is committed (POST has
                # entered its feedback-streaming phase and is now
                # blocked on ``feedback_gate``).
                for _ in range(500):
                    async with session_factory() as s:
                        a_count = (await s.execute(select(func.count()).select_from(AnswerModel))).scalar_one()
                    if a_count >= 1:
                        break
                    await asyncio.sleep(0.005)

                # Let the GET pause-loop poll a few times while F1 is
                # still blocked on ``feedback_gate``. This is only for
                # the buggy code to have had the opportunity to call
                # ``append_question`` for Q2 — if the code were buggy,
                # its timestamp would land BEFORE the gate release and
                # the assertion below would catch it.
                await asyncio.sleep(0.2)

                # Capture the release timestamp and release the gate
                # atomically. The assertion at the bottom of the test
                # compares Q2's ``append_question`` timestamp against
                # this reference point.
                feedback_gate_released_at.append(_time.monotonic())
                feedback_gate.set()

                post_resp_q1 = await post_task_q1
                assert post_resp_q1.status_code == 200

                # Wait for Q2 to land so we can POST its answer and
                # let the GET stream close cleanly.
                for _ in range(500):
                    async with session_factory() as s:
                        q_count = (await s.execute(select(func.count()).select_from(QuestionModel))).scalar_one()
                    if q_count >= 2:
                        break
                    await asyncio.sleep(0.01)

                post_resp_q2 = await ac.post(
                    f"/api/v1/sessions/{seeded['author_id']}/answers",
                    headers=_bearer(seeded["user_id"]),
                    json={"question_number": 2, "text": "my answer to Q2"},
                )
                assert post_resp_q2.status_code == 200

        stream_task = asyncio.create_task(drive_get_stream())
        poster_task = asyncio.create_task(post_answers_with_race_observation())

        frames = await asyncio.wait_for(stream_task, timeout=30.0)
        await asyncio.wait_for(poster_task, timeout=15.0)

        # Load-bearing assertion for the BLOCKER #4 fix (v1.3.0 review
        # P3): Q2's ``append_question`` timestamp MUST be strictly
        # greater than ``feedback_gate_released_at``. This is a
        # deterministic, timing-window-free check — if the pause-loop
        # were to advance on ``count_answers`` alone, it would call
        # ``append_question`` during the ~200 ms the gate was held,
        # and Q2's timestamp would predate the release.
        assert len(feedback_gate_released_at) == 1, (
            f"test bug: feedback_gate was not released exactly once — release_count={len(feedback_gate_released_at)}"
        )
        assert len(append_question_timestamps) == 2, (
            f"expected exactly two append_question calls (Q1 + Q2); got {len(append_question_timestamps)}"
        )
        q1_appended_at, q2_appended_at = append_question_timestamps
        released_at = feedback_gate_released_at[0]
        assert q2_appended_at > released_at, (
            "BLOCKER #4 regression: Q2 was appended to the DB "
            f"{released_at - q2_appended_at:.3f}s BEFORE the feedback "
            "gate was released — pause-loop advanced on count_answers "
            "alone. Timestamps (monotonic): "
            f"Q1_appended={q1_appended_at:.6f}, "
            f"gate_released={released_at:.6f}, "
            f"Q2_appended={q2_appended_at:.6f}."
        )
        # Sanity: Q1 was appended BEFORE the POST ran (the GET stream
        # seeded it as the first question), so its timestamp predates
        # the gate release. This just guards against a future refactor
        # that reorders the test setup.
        assert q1_appended_at < released_at, (
            "test setup regression: Q1 was appended AFTER the gate "
            "release — the GET stream's initial question seeding no "
            "longer happens before the POST. Review the test's ordering "
            "before trusting the Q2 assertion."
        )

        # And after release, Q2 did emit normally — the GET stream's
        # frame list should contain both question frames, in order.
        question_frames = [d for (e, d) in frames if e == "question"]
        assert len(question_frames) == 2
        assert question_frames[0]["number"] == 1
        assert question_frames[1]["number"] == 2
