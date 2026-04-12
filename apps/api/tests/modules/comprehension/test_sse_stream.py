"""Integration tests for the comprehension SSE endpoint (Story 3.3).

All tests here use ``AsyncClient`` + ``ASGITransport`` — no real
Anthropic calls, no real server. The LLM stream is mocked by
dependency-override on ``get_llm_provider`` so the timing / ordering /
frame-content invariants are deterministic and CI-stable.

Key invariants locked here:

1. Happy path: ``question_token`` frames precede ``question`` frames
   precede ``done``.
2. Persistence: after the stream ends, ``questions`` table has N rows
   where N == ``session.total_questions``, each with a 64-char
   ``text_hash`` and NO ``text`` column.
3. First-token-under-1s and first-question-under-3s timing (NFR2/NFR3).
4. 404 / 403 paths return JSON error responses BEFORE any SSE frame.
5. LLM failure mid-stream → last frame is ``event: error``.
6. Missing BYOK → 422 JSON error before any stream frame.
"""

import asyncio
import hashlib
import time
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
from helprs.modules.comprehension.infrastructure.agents import PydanticAILLMProvider
from helprs.modules.comprehension.infrastructure.models import QuestionModel, SessionModel
from helprs.modules.comprehension.presentation.dependencies import get_llm_provider
from helprs.modules.identity.models import GitHubUser
from helprs.modules.installation.models import BYOKConfig, Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"

_TEST_GITHUB_USER_ID = 8888
_TEST_GITHUB_INSTALLATION_ID = 87654321


@pytest.fixture
async def app_with_db(monkeypatch):
    """App + DB + seeded installation / user / session / BYOK."""
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    application = create_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    application.state.session_factory = session_factory
    # The lifespan never runs under ASGITransport, so we register the
    # factory directly for ``get_db_context`` to pick up.
    set_session_factory(session_factory)

    settings = get_settings()

    async with session_factory() as bootstrap:
        installation = Installation(
            github_installation_id=_TEST_GITHUB_INSTALLATION_ID,
            account_login="acme",
            account_id=55556,
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
            encrypted_api_key=fernet_encrypt("sk-ant-fake", settings.FERNET_KEY),
            key_status="valid",
            validated_at=datetime.now(UTC),
            key_hint="...fake",
        )
        bootstrap.add(byok)

        user = GitHubUser(
            github_id=_TEST_GITHUB_USER_ID,
            github_login="sse_user",
            email="sse@example.com",
            avatar_url=None,
            github_access_token_enc=fernet_encrypt("gho_test_token", settings.FERNET_KEY),
        )
        bootstrap.add(user)
        await bootstrap.flush()

        author = SessionModel(
            installation_id=installation.id,
            github_installation_id=_TEST_GITHUB_INSTALLATION_ID,
            repo_full_name="acme/sseo",
            repo_owner="acme",
            repo_name="sseo",
            pr_number=7,
            pr_title="Improve foo",
            pr_head_sha="deadbeef",
            pr_diff_url="https://github.com/acme/sseo/pull/7.diff",
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
def _skip_answer_polling(monkeypatch):
    """Story 3.3 happy-path tests predate Story 3.4's pause-loop and
    never POST answers — so the new polling wait would hang forever.
    This fixture short-circuits ``_wait_for_answer_count`` to return
    immediately for those tests.

    **NEW tests that exercise the pause-loop MUST opt out** by
    using the ``_real_answer_polling`` fixture below (which resets
    the monkeypatch so the real DB-polling implementation runs and
    is driven by actual POST traffic). ``TestPauseLoopResume`` and
    ``test_answer_submission.TestGetStreamAdvancesOnAnswer`` opt out.
    """
    from helprs.modules.comprehension.presentation import sse as sse_module

    async def _no_wait(*, session_id, target, request):  # noqa: ARG001
        return None

    monkeypatch.setattr(sse_module, "_wait_for_answer_count", _no_wait)
    return _no_wait


@pytest.fixture(autouse=True)
def _patch_github_calls(monkeypatch):
    """Patch mint_installation_token + access check + diff fetch so
    the endpoint runs with deterministic upstream values.

    The LLM provider is NOT patched here — individual tests override
    ``get_llm_provider`` via ``app.dependency_overrides`` to script
    per-test token sequences.
    """
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
            "diff --git a/apps/web/bar.ts b/apps/web/bar.ts\n"
            "--- a/apps/web/bar.ts\n"
            "+++ b/apps/web/bar.ts\n"
            "@@ -1 +1 @@\n"
            "-export const bar = 1;\n"
            "+export const bar = 2;\n"
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
        {"sub": str(user_id), "github_login": "sse_user"},
        settings.SECRET_KEY,
    )
    return {"Authorization": f"Bearer {token}"}


class _ScriptedLLM:
    """Fake ``PydanticAILLMProvider`` that yields a scripted sequence.

    ``questions`` is a list of strings; ``stream_question`` is called
    once per question and the matching string is yielded character by
    character so tests can assert token-level ordering. ``delay``
    optionally introduces an awaitable pause before the first token
    (used by the NFR3 timing test).
    """

    def __init__(self, questions: list[str], first_token_delay: float = 0.0) -> None:
        self.questions = list(questions)
        self.calls = 0
        self.first_token_delay = first_token_delay
        self.api_keys_seen: list[str] = []
        # Story 3.5: capture each PRPromptContext the stream receives so
        # integration tests can assert role/title/stats wiring.
        self.pr_metadata_seen: list = []

    async def stream_question(
        self,
        *,
        pr_diff: str,
        pr_metadata,
        previous_questions,
        api_key: str,
    ) -> AsyncIterator[str]:
        self.api_keys_seen.append(api_key)
        self.pr_metadata_seen.append(pr_metadata)
        idx = self.calls
        self.calls += 1
        if idx >= len(self.questions):
            return
        text = self.questions[idx]
        if self.first_token_delay:
            await asyncio.sleep(self.first_token_delay)
        for ch in text:
            # Explicit zero-sleep yield so the event loop can ferry
            # frames to the client between chunks.
            await asyncio.sleep(0)
            yield ch

    async def generate_question(self, **kwargs) -> str:
        return "".join([q async for q in self.stream_question(**kwargs)])

    async def generate_feedback(self, **kwargs) -> str:
        raise NotImplementedError

    async def generate_score(self, **kwargs):
        from datetime import UTC, datetime

        from helprs.modules.comprehension.domain.entities import Score
        from helprs.modules.comprehension.domain.services import derive_verdict

        sid = kwargs.get("session_id") or __import__("uuid").UUID(int=0)
        verdict = derive_verdict(7, 7, 7, 7)
        return Score(
            session_id=sid,
            depth=7,
            accuracy=7,
            completeness=7,
            insight=7,
            verdict=verdict,
            gap_summary=("test gap 1", "test gap 2"),
            created_at=datetime.now(UTC),
        )


class _RaisingLLM:
    """Fake provider that yields one chunk then raises httpx.TimeoutException."""

    async def stream_question(self, **kwargs) -> AsyncIterator[str]:
        import httpx

        yield "Hel"
        raise httpx.TimeoutException("upstream timeout")

    async def generate_question(self, **kwargs) -> str:
        return "Hel"


def _override_llm(app, provider) -> None:
    app.dependency_overrides[get_llm_provider] = lambda: provider


def _parse_sse(body: bytes) -> list[tuple[str, dict]]:
    """Tiny SSE parser for tests. Returns list of (event, data) pairs."""
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


class TestHappyPath:
    async def test_streams_three_questions_then_done(self, app_with_db, _patch_github_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        scripted = _ScriptedLLM(
            [
                "What assumption are you making in apps/api/foo.py?",
                "Why does apps/web/bar.ts return 2?",
                "What edge case did you miss?",
            ]
        )
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        frames = _parse_sse(resp.content)

        # At least 1 token per question + 1 question frame per question + 1 done.
        events = [e for (e, _) in frames]
        assert events.count("question") == 3
        assert events.count("done") == 1
        assert events.count("question_token") >= 3

        # Ordering: done is the last frame.
        assert events[-1] == "done"

        # Each ``question`` frame carries the full text, number, total, refs.
        question_frames = [d for (e, d) in frames if e == "question"]
        assert [q["number"] for q in question_frames] == [1, 2, 3]
        assert all(q["total"] == 3 for q in question_frames)
        assert question_frames[0]["text"].startswith("What assumption")
        # File ref extraction picked up apps/api/foo.py in Q1.
        assert "apps/api/foo.py" in question_frames[0]["file_refs"]
        assert "apps/web/bar.ts" in question_frames[1]["file_refs"]

        # Done carries the session id + question count.
        done = [d for (e, d) in frames if e == "done"][0]
        assert done["question_count"] == 3
        assert done["session_id"] == str(seeded["author_id"])

        # BYOK key was forwarded to the LLM.
        assert scripted.api_keys_seen == ["sk-ant-fake"] * 3

    async def test_file_refs_word_boundary_rejects_prefix_collisions(self, app_with_db, _patch_github_calls):
        """P19 from story-3.3 review: the previous happy-path test
        asserted that a path appearing LITERALLY in the question text
        shows up in ``file_refs`` — tautological (a broken impl that
        returns all paths unconditionally also passes).

        This test uses a prefix-colliding pair (``foo.py`` and
        ``foo.py.bak``) and a question text that mentions ONLY the
        longer one. The extractor must return the longer path exactly
        and NOT the shorter one — the old plain-substring match would
        have returned both and failed this test.
        """
        application, session_factory, seeded = app_with_db
        _, access_list, diff_mock = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        # Override the diff fixture with a prefix-colliding pair.
        diff_mock.return_value = (
            "diff --git a/apps/api/foo.py b/apps/api/foo.py\n"
            "--- a/apps/api/foo.py\n"
            "+++ b/apps/api/foo.py\n"
            "@@ -1 +1 @@\n"
            "-x = 1\n"
            "+x = 2\n"
            "diff --git a/apps/api/foo.py.bak b/apps/api/foo.py.bak\n"
            "--- a/apps/api/foo.py.bak\n"
            "+++ b/apps/api/foo.py.bak\n"
            "@@ -1 +1 @@\n"
            "-y = 1\n"
            "+y = 2\n"
        )

        scripted = _ScriptedLLM(
            [
                # Mentions apps/api/foo.py.bak only. The extractor must
                # NOT also return apps/api/foo.py (prefix collision).
                "Why did apps/api/foo.py.bak diverge from the main file?",
                # Mentions the shorter path only. Must NOT return the
                # longer path even though the longer contains the
                # shorter as a substring.
                "What's the intent behind apps/api/foo.py?",
                "Final question?",
            ]
        )
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )

        assert resp.status_code == 200
        frames = _parse_sse(resp.content)
        question_frames = [d for (e, d) in frames if e == "question"]
        assert len(question_frames) == 3
        # Q1: mentions the longer path only.
        assert question_frames[0]["file_refs"] == ["apps/api/foo.py.bak"]
        # Q2: mentions the shorter path only.
        assert question_frames[1]["file_refs"] == ["apps/api/foo.py"]
        # Q3: mentions neither path explicitly.
        assert question_frames[2]["file_refs"] == []

    async def test_persists_text_hashes_no_text_column(self, app_with_db, _patch_github_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        scripted = _ScriptedLLM(["Q1?", "Q2?", "Q3?"])
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 200

        async with session_factory() as s:
            count = (
                await s.execute(
                    select(func.count())
                    .select_from(QuestionModel)
                    .where(QuestionModel.session_id == seeded["author_id"])
                )
            ).scalar_one()
            rows = list(
                (await s.execute(select(QuestionModel).where(QuestionModel.session_id == seeded["author_id"])))
                .scalars()
                .all()
            )

        assert count == 3
        numbers = sorted(r.number for r in rows)
        assert numbers == [1, 2, 3]
        for r in rows:
            assert len(r.text_hash) == 64
            # Defensive: no attribute named ``text`` exists on the model.
            assert not hasattr(r, "text")


class TestTiming:
    async def test_first_question_token_under_1s(self, app_with_db, _patch_github_calls):
        """NFR3: first token arrives < 1 s after request accepted."""
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        scripted = _ScriptedLLM(["Q?", "Q2?", "Q3?"], first_token_delay=0.05)
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            t0 = time.monotonic()
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
            elapsed = time.monotonic() - t0

        assert resp.status_code == 200
        frames = _parse_sse(resp.content)
        # First event in the stream must be a ``question_token``.
        assert frames[0][0] == "question_token"
        # Full round-trip under 1 s with mock delay of 50 ms.
        assert elapsed < 1.0, f"round-trip took {elapsed:.3f}s"

    async def test_first_question_event_under_3s(self, app_with_db, _patch_github_calls):
        """NFR2: first complete question arrives < 3 s after request."""
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        scripted = _ScriptedLLM(["First question here?", "Q2?", "Q3?"], first_token_delay=0.05)
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            t0 = time.monotonic()
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
            elapsed = time.monotonic() - t0

        assert resp.status_code == 200
        frames = _parse_sse(resp.content)
        # The first ``question`` frame should be present.
        first_question_index = next((i for i, (e, _) in enumerate(frames) if e == "question"), None)
        assert first_question_index is not None
        # 3 s budget from AC #6 — plenty of headroom vs the 50 ms mock.
        assert elapsed < 3.0, f"round-trip took {elapsed:.3f}s"


class TestAccessControl:
    async def test_returns_404_for_unknown_session(self, app_with_db, _patch_github_calls):
        application, _, seeded = app_with_db
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{uuid.uuid4()}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")

    async def test_returns_403_when_user_has_no_access(self, app_with_db, _patch_github_calls):
        application, _, seeded = app_with_db
        _, access_list, _ = _patch_github_calls
        access_list.return_value = []  # explicit — no installations

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 403
        assert resp.headers["content-type"].startswith("application/json")

    async def test_returns_401_without_bearer(self, app_with_db):
        application, _, seeded = app_with_db
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(f"/api/v1/sessions/{seeded['author_id']}/stream")
        assert resp.status_code == 401


class TestBYOKErrors:
    async def test_missing_byok_returns_422_before_stream(self, app_with_db, _patch_github_calls):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        # Drop BYOK config.
        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
            await s.execute(BYOKConfig.__table__.delete().where(BYOKConfig.installation_id == inst.id))
            await s.commit()
        access_list.return_value = [inst]

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        # DomainValidationError → 422
        assert resp.status_code == 422
        assert resp.headers["content-type"].startswith("application/json")


class TestLLMError:
    async def test_llm_failure_emits_error_frame(self, app_with_db, _patch_github_calls):
        """P18 from story-3.3 review: assertions no longer couple to
        the specific httpx exception CLASS NAME ("TimeoutException").
        Instead we assert the shape of the error frame (all required
        fields present, stream ended with error), which survives any
        future switch to a different upstream exception type or a
        stable internal error taxonomy.
        """
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        _override_llm(application, _RaisingLLM())

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 200  # the stream opened before the error
        frames = _parse_sse(resp.content)
        events = [e for (e, _) in frames]
        # The last frame is an `error` frame — the stream never emitted
        # `done` because generation failed mid-flight.
        assert events[-1] == "error"
        assert "done" not in events
        err_payload = frames[-1][1]
        # Error payload shape — lock on keys, not on class names.
        assert set(err_payload.keys()) >= {"error", "message", "retryable"}
        assert isinstance(err_payload["error"], str) and err_payload["error"]
        assert isinstance(err_payload["message"], str) and err_payload["message"]
        assert err_payload["retryable"] is True
        # And an error after only a partial token stream must NOT
        # persist a half-streamed question (P11 from review).
        async with session_factory() as s:
            count = (
                await s.execute(
                    select(func.count())
                    .select_from(QuestionModel)
                    .where(QuestionModel.session_id == seeded["author_id"])
                )
            ).scalar_one()
        assert count == 0


class TestClientDisconnect:
    """P25 from story-3.3 review: Task 6.2 required a client-disconnect
    regression test and it was missing. These tests lock the contract
    that (a) the generator's ``is_disconnected`` check short-circuits
    the LLM loop cleanly, and (b) an ``asyncio.CancelledError`` from
    the ASGI layer does not leave behind a half-persisted question.
    """

    async def test_disconnect_between_questions_stops_generation(self, app_with_db, _patch_github_calls, monkeypatch):
        """Simulate ``request.is_disconnected()`` returning True after
        the first question commits. The generator must exit cleanly,
        persist exactly 1 question, and never yield ``done``.
        """
        from starlette.requests import Request as StarletteRequest

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        # Single-character questions so ``is_disconnected`` is called
        # a predictable number of times per question: 1 outer gate +
        # 1 inner token check = 2 calls to finish one question.
        scripted = _ScriptedLLM(["Q", "Q", "Q"])
        _override_llm(application, scripted)

        # Patch ``is_disconnected`` to return False for Q1 (calls 1-2),
        # then True from call 3 onward (Q2's outer gate). Q1 commits
        # fully, Q2's generation never starts.
        calls = {"n": 0}
        original = StarletteRequest.is_disconnected

        async def fake_is_disconnected(self):  # noqa: ARG001
            calls["n"] += 1
            return calls["n"] > 2

        monkeypatch.setattr(StarletteRequest, "is_disconnected", fake_is_disconnected)

        try:
            async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
                resp = await ac.get(
                    f"/api/v1/sessions/{seeded['author_id']}/stream",
                    headers=_bearer(seeded["user_id"]),
                )
            assert resp.status_code == 200
            frames = _parse_sse(resp.content)
            events = [e for (e, _) in frames]
            # At least one ``question`` frame got through before the
            # disconnect signal fired; ``done`` must NOT appear.
            assert "question" in events
            assert "done" not in events
        finally:
            monkeypatch.setattr(StarletteRequest, "is_disconnected", original)

        # DB holds only fully-committed questions — never a
        # half-streamed row, never a row without a real text_hash.
        async with session_factory() as s:
            rows = list(
                (await s.execute(select(QuestionModel).where(QuestionModel.session_id == seeded["author_id"])))
                .scalars()
                .all()
            )
        assert 0 <= len(rows) <= 3
        for r in rows:
            assert len(r.text_hash) == 64  # full SHA-256 hex
            assert r.number >= 1


class TestSseFrameHelper:
    def test_sse_frame_encoding(self):
        """Round-trip: encoded frame parses back to the original dict.

        P17 from story-3.3 review: the previous assertion relied on a
        substring match with a specific `json.dumps` separator, which
        would silently break if anyone switched to compact separators.
        Parsing + comparing the deserialized dict locks the wire
        contract without coupling to the formatter's whitespace.
        """
        import json as _json

        from helprs.modules.comprehension.presentation.sse import _sse_frame

        encoded = _sse_frame("question_token", {"token": "hi", "number": 1})
        assert encoded.startswith(b"event: question_token\n")
        assert encoded.endswith(b"\n\n")
        # Parse back: event + payload equal what we put in.
        text = encoded.decode("utf-8")
        assert text.startswith("event: question_token\n")
        data_line = next(line for line in text.splitlines() if line.startswith("data: "))
        payload = _json.loads(data_line.removeprefix("data: "))
        assert payload == {"token": "hi", "number": 1}


class TestProviderKeyHygiene:
    async def test_pydantic_ai_provider_uses_fresh_key_per_call(self, monkeypatch):
        """Behavioral zero-retention check (P16 from story-3.3 review).

        The previous test asserted ``not hasattr(provider, "_api_key")``
        which passes trivially for any class that doesn't initialize
        that specific attribute name. A malicious implementation could
        stash the key under ``_cfg``, ``_key``, a class-level dict, etc.
        and still pass.

        This test is behavioral: monkeypatches ``_build_agent`` — the
        seam exposed specifically for this purpose — to record the key
        passed to it, then calls ``stream_question`` twice with
        different keys. Each call must use its own key; neither key
        may appear on the provider instance after both calls return.
        """
        from helprs.modules.comprehension.domain.value_objects import SessionRole
        from helprs.modules.comprehension.infrastructure.agents import PRPromptContext

        keys_seen: list[str] = []

        class _StubRunStream:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return None

            async def stream_text(self, delta: bool = False):
                yield "chunk"

        class _StubAgent:
            def run_stream(self, prompt: str):
                return _StubRunStream()

        def _stub_build_agent(self, api_key: str, *, role: SessionRole):  # noqa: ARG001
            keys_seen.append(api_key)
            return _StubAgent()

        monkeypatch.setattr(PydanticAILLMProvider, "_build_agent", _stub_build_agent)

        provider = PydanticAILLMProvider()
        metadata = PRPromptContext(
            role=SessionRole.AUTHOR,
            pr_title="Test",
            total_lines_changed=0,
            changed_file_count=0,
            file_stats=(),
        )

        async for _ in provider.stream_question(
            pr_diff="diff", pr_metadata=metadata, previous_questions=[], api_key="key-A"
        ):
            pass
        async for _ in provider.stream_question(
            pr_diff="diff", pr_metadata=metadata, previous_questions=[], api_key="key-B"
        ):
            pass

        # Each call must have constructed a fresh Agent with its own
        # key — no caching, no leakage across calls.
        assert keys_seen == ["key-A", "key-B"]
        # And neither key appears on the provider instance after both
        # calls return — ``vars(provider)`` should still be empty.
        for v in vars(provider).values():
            assert "key-A" not in str(v)
            assert "key-B" not in str(v)


class TestReconnectReplay:
    """Story 3.4 kick-back regression (2026-04-11 manual QA BLOCKER #1).

    Reconnecting to an SSE stream for a session that has existing
    UNANSWERED questions must REPLAY those questions, not regenerate
    new ones at ``max(number) + 1``. The original v1.1.0 pause-loop
    rewrite preserved this property only for the FIRST connection;
    every subsequent connection blindly called ``append_question`` and
    advanced the question cursor without an answer ever being
    submitted, which is the exact regression Project Lead manual QA
    surfaced. The fix is in ``stream_session``: snapshot
    ``list_questions`` in the DB phase and take the replay branch
    when ``existing_by_number[_loop_number]`` is set.
    """

    async def test_reconnect_replays_existing_q1_does_not_generate_q2(self, app_with_db, _patch_github_calls):
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )
        from helprs.modules.comprehension.presentation.answer_pubsub import (
            stash_question_text,
        )

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        # Pre-seed Q1 in the DB AND in the in-memory registry, mimicking
        # a prior SSE connection that committed Q1 and then disconnected
        # before any answer landed.
        original_q1_text = "What's the assumption you made in foo.py?"
        async with session_factory() as s:
            repo = SqlAlchemySessionRepository(s)
            q1 = await repo.append_question(
                session_id=seeded["author_id"],
                topic=Topic.ARCHITECTURE,
                text_hash=hashlib.sha256(original_q1_text.encode()).hexdigest(),
            )
            await s.commit()
        stash_question_text(seeded["author_id"], q1.id, original_q1_text)
        original_q1_id = str(q1.id)

        # Override the LLM with a sentinel for slot 1 — if it ever gets
        # called for Q1, the test fails because Q1 was supposed to be
        # replayed from the registry. Slots 2 and 3 hold the legitimate
        # generation responses.
        scripted = _ScriptedLLM(
            [
                "REGENERATED_BUG_Q1_SHOULD_NOT_APPEAR",
                "Why does bar.ts return 2?",
                "What edge case did you miss?",
            ]
        )
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )

        assert resp.status_code == 200
        frames = _parse_sse(resp.content)
        question_frames = [d for (e, d) in frames if e == "question"]
        assert len(question_frames) == 3

        # Q1 must be the REPLAY (same question_id as the pre-seeded
        # row, original text, NOT the LLM sentinel).
        assert question_frames[0]["number"] == 1
        assert question_frames[0]["text"] == original_q1_text
        assert question_frames[0]["question_id"] == original_q1_id
        assert "REGENERATED_BUG" not in question_frames[0]["text"]

        # Q2 / Q3 are fresh generation, so they DO come from the LLM.
        assert question_frames[1]["number"] == 2
        assert question_frames[2]["number"] == 3

        # Critically: the LLM was called only TWICE (for Q2 and Q3).
        # If the bug regressed, ``stream_question`` would have been
        # called THREE times because Q1 would have been regenerated.
        assert scripted.calls == 2

        # And the DB still has exactly 3 question rows — replay must
        # not produce a duplicate Q1 row at number=4 or anywhere else.
        async with session_factory() as s:
            db_count = (
                await s.execute(
                    select(func.count())
                    .select_from(QuestionModel)
                    .where(QuestionModel.session_id == seeded["author_id"])
                )
            ).scalar_one()
            db_numbers = sorted(
                r.number
                for r in (await s.execute(select(QuestionModel).where(QuestionModel.session_id == seeded["author_id"])))
                .scalars()
                .all()
            )
        assert db_count == 3
        assert db_numbers == [1, 2, 3]

    async def test_reconnect_with_cold_registry_emits_error(self, app_with_db, _patch_github_calls):
        """Companion case: a question exists in the DB but the in-memory
        text registry was cleared (server restart between connections).
        The stream must emit a structured ``error`` frame rather than
        ploughing on with stale assumptions.
        """
        from helprs.modules.comprehension.domain.value_objects import Topic
        from helprs.modules.comprehension.infrastructure.repositories import (
            SqlAlchemySessionRepository,
        )
        from helprs.modules.comprehension.presentation.answer_pubsub import (
            reset_answer_pubsub,
        )

        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        # Q1 exists in the DB but NOT in the registry.
        async with session_factory() as s:
            repo = SqlAlchemySessionRepository(s)
            await repo.append_question(
                session_id=seeded["author_id"],
                topic=Topic.ARCHITECTURE,
                text_hash="a" * 64,
            )
            await s.commit()
        reset_answer_pubsub()

        scripted = _ScriptedLLM(["should not be reached"])
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )

        assert resp.status_code == 200
        frames = _parse_sse(resp.content)
        events = [e for (e, _) in frames]
        assert "error" in events
        # The error frame is the LAST one (we return immediately).
        assert events[-1] == "error"
        err = next(d for (e, d) in frames if e == "error")
        assert err["error"] == "question_text_unavailable_after_restart"
        # The LLM was never called: nothing was generated.
        assert scripted.calls == 0


# ----------------------------------------------------------------------
# Story 3.5: pr_metadata wiring + large-PR ranking in stream_session
# ----------------------------------------------------------------------


def _make_large_diff(file_sizes: list[tuple[str, int, int]]) -> str:
    """Build a synthetic unified diff from a list of (path, add, del)
    tuples. Each file gets ``add`` added-lines and ``del`` deleted-lines
    of filler content.
    """
    sections: list[str] = []
    for path, additions, deletions in file_sizes:
        lines = [
            f"diff --git a/{path} b/{path}",
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -1 +1 @@",
        ]
        for i in range(additions):
            lines.append(f"+added_{i}")
        for i in range(deletions):
            lines.append(f"-deleted_{i}")
        sections.append("\n".join(lines))
    return "\n".join(sections)


class TestStory35PRPromptContext:
    """Story 3.5 AC #15: the SSE stream must build a ``PRPromptContext``
    that carries the session role, the PR title, the computed
    ``total_lines_changed``, and the per-file stats tuple, and forward
    it into ``llm.stream_question`` in place of the old bare ``role``.
    """

    async def test_stream_session_builds_pr_metadata_for_author_session(
        self, app_with_db, _patch_github_calls, monkeypatch
    ):
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls

        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        # 300-line diff — below the 2000-line ranking threshold.
        small_diff = _make_large_diff(
            [
                ("apps/api/foo.py", 100, 50),
                ("apps/web/bar.ts", 100, 50),
            ]
        )
        monkeypatch.setattr(
            "helprs.modules.comprehension.presentation.sse.fetch_pr_diff",
            _const_coro(small_diff),
        )

        scripted = _ScriptedLLM(["Q1?", "Q2?", "Q3?"])
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 200

        assert len(scripted.pr_metadata_seen) >= 1
        first_meta = scripted.pr_metadata_seen[0]
        # Author session from the seeded fixture.
        assert first_meta.role.value == "author"
        # PR title from the seeded session row.
        assert first_meta.pr_title == "Improve foo"
        # Total lines = additions + deletions across both files.
        assert first_meta.total_lines_changed == 300
        # Two changed files in the diff.
        assert first_meta.changed_file_count == 2
        # Stats tuple carries one entry per file.
        assert len(first_meta.file_stats) == 2
        paths = {s.path for s in first_meta.file_stats}
        assert paths == {"apps/api/foo.py", "apps/web/bar.ts"}

    async def test_stream_session_skips_ranking_for_small_pr(self, app_with_db, _patch_github_calls, monkeypatch):
        """AC #15: below the 2000-line threshold, ``select_and_rank_files``
        is NOT called; the diff seen by the LLM matches the fetched diff
        byte-for-byte.
        """
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls
        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        small_diff = _make_large_diff([("x.py", 100, 100)])
        monkeypatch.setattr(
            "helprs.modules.comprehension.presentation.sse.fetch_pr_diff",
            _const_coro(small_diff),
        )

        call_count = {"n": 0}
        original_rank = __import__(
            "helprs.modules.comprehension.presentation.sse",
            fromlist=["select_and_rank_files"],
        ).select_and_rank_files

        def spy(diff, stats=None):
            call_count["n"] += 1
            return original_rank(diff, stats=stats)

        monkeypatch.setattr(
            "helprs.modules.comprehension.presentation.sse.select_and_rank_files",
            spy,
        )

        # Capture what the LLM received as pr_diff.
        captured: dict = {}

        class _CapturingLLM(_ScriptedLLM):
            async def stream_question(self, *, pr_diff, pr_metadata, previous_questions, api_key):
                captured.setdefault("diff", pr_diff)
                async for c in super().stream_question(
                    pr_diff=pr_diff,
                    pr_metadata=pr_metadata,
                    previous_questions=previous_questions,
                    api_key=api_key,
                ):
                    yield c

        scripted = _CapturingLLM(["Q1?", "Q2?", "Q3?"])
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 200

        assert call_count["n"] == 0, "select_and_rank_files should not be called for small PRs"
        assert captured["diff"] == small_diff

    async def test_stream_session_ranks_diff_for_huge_pr(self, app_with_db, _patch_github_calls, monkeypatch):
        """AC #15: at/above the 2000-line threshold, ``select_and_rank_files``
        is invoked and its output (not the raw fetch) goes into the LLM.
        """
        application, session_factory, seeded = app_with_db
        _, access_list, _ = _patch_github_calls
        async with session_factory() as s:
            inst = (
                await s.execute(select(Installation).where(Installation.id == seeded["installation_id"]))
            ).scalar_one()
        access_list.return_value = [inst]

        huge_diff = _make_large_diff(
            [
                ("dominant.py", 1500, 0),
                ("moderate.py", 800, 0),
                ("small.py", 200, 0),
            ]
        )
        monkeypatch.setattr(
            "helprs.modules.comprehension.presentation.sse.fetch_pr_diff",
            _const_coro(huge_diff),
        )

        call_inputs: list[tuple[str, object]] = []

        def rank_spy(diff, stats=None):
            call_inputs.append((diff, stats))
            # Return a sentinel diff so we can assert it flows into the LLM.
            return "RANKED_DIFF_SENTINEL", stats or []

        monkeypatch.setattr(
            "helprs.modules.comprehension.presentation.sse.select_and_rank_files",
            rank_spy,
        )

        captured: dict = {}

        class _CapturingLLM(_ScriptedLLM):
            async def stream_question(self, *, pr_diff, pr_metadata, previous_questions, api_key):
                captured.setdefault("diff", pr_diff)
                async for c in super().stream_question(
                    pr_diff=pr_diff,
                    pr_metadata=pr_metadata,
                    previous_questions=previous_questions,
                    api_key=api_key,
                ):
                    yield c

        scripted = _CapturingLLM(["Q1?", "Q2?", "Q3?"])
        _override_llm(application, scripted)

        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
            resp = await ac.get(
                f"/api/v1/sessions/{seeded['author_id']}/stream",
                headers=_bearer(seeded["user_id"]),
            )
        assert resp.status_code == 200

        # Ranking was called exactly once with a diff whose measured
        # total_lines >= 2000.
        assert len(call_inputs) == 1
        # Second arg is the stats list — its total should be 2500.
        _, stats = call_inputs[0]
        total = sum(s.total_lines for s in stats)
        assert total == 2500
        # The LLM received the ranked sentinel, NOT the raw fetched diff.
        assert captured["diff"] == "RANKED_DIFF_SENTINEL"

        # Story 3.5 code-review patch (P5 / AC #15): the PRPromptContext
        # forwarded to the LLM must carry the PRE-RANKING totals so the
        # LLM knows the full scope of the change even though the diff
        # body was trimmed. This is the AC #7 contract surface ("the
        # prompt still shows stats for every file so the LLM knows
        # what it is NOT seeing").
        assert len(scripted.pr_metadata_seen) >= 1
        meta = scripted.pr_metadata_seen[0]
        assert meta.total_lines_changed == 2500
        assert len(meta.file_stats) == 3
        assert {s.path for s in meta.file_stats} == {"dominant.py", "moderate.py", "small.py"}


def _const_coro(value):
    """Return an AsyncMock-like callable that returns ``value``."""
    from unittest.mock import AsyncMock

    return AsyncMock(return_value=value)
