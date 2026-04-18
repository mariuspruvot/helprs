"""Tests for score card extraction and PR comment formatting."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from helprs.core.config import get_settings
from helprs.core.database import Base, clear_session_factory, set_session_factory
from helprs.modules.container.models import ContainerSession, ContainerStatus, SessionEvent
from helprs.modules.container.pr_comment import build_session_url, extract_score_card, format_pr_comment
from helprs.modules.installation.models import Installation

TEST_DATABASE_URL = "postgresql+asyncpg://helprs:helprs@localhost:5432/helprs_test"

SAMPLE_SCORE_CARD = """\
Some conversation text here.

---

## Results

**Questions:** 4

### Score: 7.5 / 10  ████████░░ Strong

### Dimensions

| Dimension | Rating |
|-----------|--------|
| Depth | High |
| Accuracy | High |
| Completeness | Medium |
| Insight | Medium |

### Strengths
- Good understanding of the caching layer

### Areas to Improve
- Review edge cases in error handling

### Verdict
Ready for review -- you have a strong command of this PR.

---"""


@pytest.fixture
async def db_with_session():
    """Provide a database session with a pre-seeded container session."""
    get_settings.cache_clear()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    set_session_factory(session_factory)

    async with session_factory() as session:
        installation = Installation(
            github_installation_id=11111111,
            account_login="test-org",
            account_id=22222222,
            account_type="User",
            repository_selection="all",
            app_slug="helprs",
            target_type="User",
        )
        session.add(installation)
        await session.flush()

        cs = ContainerSession(
            installation_id=installation.id,
            pr_number=42,
            repo_full_name="org/repo",
            skill_name="challenge-me",
            status=ContainerStatus.COMPLETED,
            container_id="fake-container",
        )
        session.add(cs)
        await session.commit()

        yield session, cs

    clear_session_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


class TestExtractScoreCard:
    async def test_extracts_score_card_from_result_event(self, db_with_session):
        session, cs = db_with_session

        event = SessionEvent(
            session_id=cs.id,
            event_id=1,
            data={"type": "result", "result": SAMPLE_SCORE_CARD},
        )
        session.add(event)
        await session.flush()

        result = await extract_score_card(cs.id, session)
        assert result is not None
        assert result.startswith("## Results")
        assert "Score: 7.5 / 10" in result
        assert "Ready for review" in result

    async def test_returns_none_when_no_result_event(self, db_with_session):
        session, cs = db_with_session

        event = SessionEvent(
            session_id=cs.id,
            event_id=1,
            data={"type": "assistant", "message": {"content": "Hello"}},
        )
        session.add(event)
        await session.flush()

        result = await extract_score_card(cs.id, session)
        assert result is None

    async def test_returns_none_when_no_results_heading(self, db_with_session):
        session, cs = db_with_session

        event = SessionEvent(
            session_id=cs.id,
            event_id=1,
            data={"type": "result", "result": "Just some text without a score card"},
        )
        session.add(event)
        await session.flush()

        result = await extract_score_card(cs.id, session)
        assert result is None

    async def test_returns_none_when_result_field_missing(self, db_with_session):
        session, cs = db_with_session

        event = SessionEvent(
            session_id=cs.id,
            event_id=1,
            data={"type": "result", "subtype": "done"},
        )
        session.add(event)
        await session.flush()

        result = await extract_score_card(cs.id, session)
        assert result is None

    async def test_uses_last_result_event(self, db_with_session):
        """When multiple result events exist (multi-turn), use the last one."""
        session, cs = db_with_session

        event1 = SessionEvent(
            session_id=cs.id,
            event_id=1,
            data={"type": "result", "result": "First turn result without score card"},
        )
        event2 = SessionEvent(
            session_id=cs.id,
            event_id=2,
            data={"type": "result", "result": SAMPLE_SCORE_CARD},
        )
        session.add_all([event1, event2])
        await session.flush()

        result = await extract_score_card(cs.id, session)
        assert result is not None
        assert "Score: 7.5 / 10" in result


class TestFormatPrComment:
    def test_includes_score_card(self):
        score_card = "## Results\n\n**Questions:** 3\n\n### Score: 8 / 10"
        result = format_pr_comment(score_card, "http://test.local/session/abc/org/repo/1")

        assert "### helPRs Challenge-Me Results" in result
        assert score_card in result

    def test_includes_session_link(self):
        url = "http://test.local/session/abc/org/repo/42"
        result = format_pr_comment("## Results\n\nScore: 8", url)

        assert f"[Open full Q&A session]({url})" in result

    def test_includes_collapsible_details(self):
        result = format_pr_comment("## Results", "http://test.local/session/abc/org/repo/1")

        assert "<details>" in result
        assert "</details>" in result
        assert "View session" in result


class TestBuildSessionUrl:
    def test_builds_correct_url(self):
        result = build_session_url(
            app_base_url="https://app.helprs.dev",
            installation_id=uuid.UUID("12345678-1234-1234-1234-123456789abc"),
            repo_full_name="org/repo",
            pr_number=42,
        )

        assert result == "https://app.helprs.dev/session/12345678-1234-1234-1234-123456789abc/org/repo/42"
