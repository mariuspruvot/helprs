"""Unit tests for ``PydanticAILLMProvider``.

P21 from story-3.3 review: Task 4.5 of the story required
``test_agents.py`` and it was missing. Only the fake ``_ScriptedLLM``
was exercised via the SSE endpoint, leaving ``_build_agent``,
``_render_prompt`` and the streaming plumbing itself with zero direct
coverage.

These tests monkeypatch the ``_build_agent`` seam to avoid any real
Anthropic traffic while still exercising:

* ``stream_question`` yields chunks in order from ``run_stream``
* the chunks concatenate to non-empty text
* ``generate_question`` returns the concatenation
* ``_render_prompt`` surfaces role + previous-question history
* a fresh ``Agent`` is constructed on every call (zero-retention)
"""

from collections.abc import AsyncIterator

import pytest

from helprs.modules.comprehension.domain.value_objects import SessionRole
from helprs.modules.comprehension.infrastructure.agents import (
    FEEDBACK_SYSTEM_PROMPT,
    QUESTION_SYSTEM_PROMPT,
    NullLLMProvider,
    PydanticAILLMProvider,
)


class _StubRunStream:
    """Fake ``agent.run_stream`` context manager.

    Yields a preset list of deltas from ``stream_text(delta=True)``.
    """

    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def stream_text(self, delta: bool = False) -> AsyncIterator[str]:  # noqa: ARG002
        for d in self._deltas:
            yield d


class _StubAgent:
    def __init__(self, deltas: list[str]) -> None:
        self._deltas = deltas

    def run_stream(self, prompt: str):
        return _StubRunStream(self._deltas)


class TestStreamQuestion:
    async def test_yields_chunks_in_order(self, monkeypatch):
        provider = PydanticAILLMProvider()
        monkeypatch.setattr(
            PydanticAILLMProvider,
            "_build_agent",
            lambda self, api_key: _StubAgent(["What ", "did ", "you ", "assume?"]),
        )

        chunks: list[str] = []
        async for c in provider.stream_question(
            pr_diff="diff", role=SessionRole.AUTHOR, previous_questions=[], api_key="sk-x"
        ):
            chunks.append(c)

        assert chunks == ["What ", "did ", "you ", "assume?"]
        assert "".join(chunks) == "What did you assume?"
        assert "".join(chunks) != ""  # not empty

    async def test_fresh_agent_per_call(self, monkeypatch):
        """Zero-retention: ``_build_agent`` must be invoked exactly
        once per ``stream_question`` call, not cached across calls.
        """
        call_count = {"n": 0}
        keys_seen: list[str] = []

        def build(self, api_key: str):
            call_count["n"] += 1
            keys_seen.append(api_key)
            return _StubAgent(["chunk"])

        monkeypatch.setattr(PydanticAILLMProvider, "_build_agent", build)

        provider = PydanticAILLMProvider()
        for _ in range(3):
            async for _c in provider.stream_question(
                pr_diff="diff", role=SessionRole.AUTHOR, previous_questions=[], api_key="sk-1"
            ):
                pass

        assert call_count["n"] == 3
        assert keys_seen == ["sk-1", "sk-1", "sk-1"]


class TestGenerateQuestion:
    async def test_returns_concatenation_of_stream(self, monkeypatch):
        monkeypatch.setattr(
            PydanticAILLMProvider,
            "_build_agent",
            lambda self, api_key: _StubAgent(["Why ", "not ", "split?"]),
        )
        provider = PydanticAILLMProvider()

        text = await provider.generate_question(
            pr_diff="diff", role=SessionRole.REVIEWER, previous_questions=[], api_key="sk-x"
        )
        assert text == "Why not split?"


class TestRenderPrompt:
    def test_surfaces_role_and_empty_history_marker(self):
        provider = PydanticAILLMProvider()
        prompt = provider._render_prompt(
            pr_diff="DIFF_BODY",
            role=SessionRole.AUTHOR,
            previous_questions=[],
        )
        assert "Role: author" in prompt
        assert "DIFF_BODY" in prompt
        assert "(none yet" in prompt
        # System prompt sits on the Agent, not on the per-call prompt —
        # make sure we didn't accidentally inline it here.
        assert QUESTION_SYSTEM_PROMPT not in prompt

    def test_lists_previous_questions_in_order(self):
        provider = PydanticAILLMProvider()
        prompt = provider._render_prompt(
            pr_diff="diff",
            role=SessionRole.REVIEWER,
            previous_questions=["What was Q1?", "Then Q2?"],
        )
        assert "Role: reviewer" in prompt
        assert "- What was Q1?" in prompt
        assert "- Then Q2?" in prompt
        # Q1 appears before Q2 in the rendered list.
        assert prompt.index("What was Q1?") < prompt.index("Then Q2?")


class TestNullProviderStillRaises:
    """Sanity: ``NullLLMProvider`` is retained for placeholder use in
    DI-smoke tests, and it must still raise on every call so a
    mis-wired production path fails loud.
    """

    async def test_stream_question_raises(self):
        provider = NullLLMProvider()
        with pytest.raises(NotImplementedError):
            # stream_question is declared ``async def`` but raises at
            # call time — not inside an ``async for``.
            provider.stream_question(pr_diff="", role=SessionRole.AUTHOR, previous_questions=[], api_key="")

    async def test_generate_question_raises(self):
        provider = NullLLMProvider()
        with pytest.raises(NotImplementedError):
            await provider.generate_question(pr_diff="", role=SessionRole.AUTHOR, previous_questions=[], api_key="")

    async def test_stream_feedback_raises(self):
        """Story 3.4 P15: NullLLMProvider.stream_feedback is an async
        generator matching the real provider's shape. The raise fires
        when the caller iterates, not when it calls the method.
        """
        provider = NullLLMProvider()
        gen = provider.stream_feedback(
            question_text="",
            answer_text="",
            pr_diff="",
            role=SessionRole.AUTHOR,
            api_key="",
        )
        with pytest.raises(NotImplementedError):
            async for _ in gen:
                pass

    async def test_generate_feedback_raises(self):
        provider = NullLLMProvider()
        with pytest.raises(NotImplementedError):
            await provider.generate_feedback(
                question_text="",
                answer_text="",
                pr_diff="",
                role=SessionRole.AUTHOR,
                api_key="",
            )


# ----------------------------------------------------------------------
# Story 3.4 Task 3.7: feedback agent tests. Mirror of TestStreamQuestion
# but exercises the ``_build_feedback_agent`` seam so the question and
# feedback paths can be faked independently.
# ----------------------------------------------------------------------


class TestStreamFeedback:
    async def test_yields_chunks_in_order(self, monkeypatch):
        provider = PydanticAILLMProvider()
        monkeypatch.setattr(
            PydanticAILLMProvider,
            "_build_feedback_agent",
            lambda self, api_key: _StubAgent(["Good ", "point ", "but...", " line 47?"]),
        )

        chunks: list[str] = []
        async for c in provider.stream_feedback(
            question_text="Why X?",
            answer_text="Because Y.",
            pr_diff="diff",
            role=SessionRole.AUTHOR,
            api_key="sk-x",
        ):
            chunks.append(c)

        assert chunks == ["Good ", "point ", "but...", " line 47?"]
        assert "".join(chunks) == "Good point but... line 47?"

    async def test_fresh_feedback_agent_per_call(self, monkeypatch):
        """Zero-retention: ``_build_feedback_agent`` invoked once per call,
        and the API key is forwarded to it each time without caching.
        """
        call_count = {"n": 0}
        keys_seen: list[str] = []

        def build(self, api_key: str):
            call_count["n"] += 1
            keys_seen.append(api_key)
            return _StubAgent(["chunk"])

        monkeypatch.setattr(PydanticAILLMProvider, "_build_feedback_agent", build)

        provider = PydanticAILLMProvider()
        for key in ("sk-1", "sk-2", "sk-3"):
            async for _c in provider.stream_feedback(
                question_text="q",
                answer_text="a",
                pr_diff="d",
                role=SessionRole.REVIEWER,
                api_key=key,
            ):
                pass

        assert call_count["n"] == 3
        assert keys_seen == ["sk-1", "sk-2", "sk-3"]


class TestGenerateFeedback:
    async def test_returns_concatenation_of_stream(self, monkeypatch):
        monkeypatch.setattr(
            PydanticAILLMProvider,
            "_build_feedback_agent",
            lambda self, api_key: _StubAgent(["Nice ", "catch."]),
        )
        provider = PydanticAILLMProvider()

        text = await provider.generate_feedback(
            question_text="q",
            answer_text="a",
            pr_diff="d",
            role=SessionRole.AUTHOR,
            api_key="sk-x",
        )
        assert text == "Nice catch."


class TestRenderFeedbackPrompt:
    def test_surfaces_role_question_answer_and_diff(self):
        provider = PydanticAILLMProvider()
        prompt = provider._render_feedback_prompt(
            question_text="QUESTION_BODY",
            answer_text="ANSWER_BODY",
            pr_diff="DIFF_BODY",
            role=SessionRole.AUTHOR,
        )
        assert "Role: author" in prompt
        assert "QUESTION_BODY" in prompt
        assert "ANSWER_BODY" in prompt
        assert "DIFF_BODY" in prompt
        # System prompt sits on the Agent, not on the per-call prompt.
        assert FEEDBACK_SYSTEM_PROMPT not in prompt
