"""Concrete ``LLMProvider`` implementations.

Story 3.1 ships only the ``NullLLMProvider`` stub — just enough for DI
wiring to compile and for tests that need a placeholder. The real
``PydanticAILLMProvider`` arrives in Story 3.3 alongside the
``pydantic-ai`` dependency (see architecture.md AR3).
"""

from helprs.modules.comprehension.domain.value_objects import SessionRole


class NullLLMProvider:
    """Placeholder ``LLMProvider`` that raises on every call.

    Satisfies the ``LLMProvider`` structural Protocol from
    ``domain/interfaces.py`` so the DI container can resolve it during
    the stretch where the port exists but the PydanticAI implementation
    doesn't yet.
    """

    async def generate_question(
        self,
        *,
        pr_diff: str,
        role: SessionRole,
        previous_questions: list[str],
        api_key: str,
    ) -> str:
        raise NotImplementedError("LLMProvider is wired in Story 3.3")

    async def generate_feedback(
        self,
        *,
        question: str,
        answer: str,
        pr_diff: str,
        api_key: str,
    ) -> str:
        raise NotImplementedError("LLMProvider is wired in Story 3.3")
