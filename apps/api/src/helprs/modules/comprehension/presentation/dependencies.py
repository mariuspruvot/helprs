"""Comprehension-specific FastAPI dependencies.

Story 3.3 adds ``get_llm_provider`` — the DI factory for the production
``PydanticAILLMProvider``. Kept intentionally trivial so test overrides
via ``app.dependency_overrides[get_llm_provider]`` work the standard
FastAPI way.
"""

from helprs.modules.comprehension.infrastructure.agents import PydanticAILLMProvider


def get_llm_provider() -> PydanticAILLMProvider:
    """Return a fresh ``PydanticAILLMProvider`` instance.

    Stateless, cheap to construct. A new provider per request is
    semantically identical to a shared one (the BYOK key is passed at
    call time, never cached), but constructing per-request keeps the
    dep graph simple and avoids ordering issues with the lifespan.
    """
    return PydanticAILLMProvider()
