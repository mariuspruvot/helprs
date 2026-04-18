"""Unit tests for post_results_to_pr setting service."""

from helprs.modules.installation.service import update_post_results_setting


class TestUpdatePostResultsSetting:
    async def test_enable(self, db_session, test_installation):
        result = await update_post_results_setting(db_session, test_installation.id, enabled=True)
        assert result.post_results_to_pr is True

    async def test_disable(self, db_session, test_installation):
        test_installation.post_results_to_pr = True
        await db_session.flush()

        result = await update_post_results_setting(db_session, test_installation.id, enabled=False)
        assert result.post_results_to_pr is False

    async def test_default_is_false(self, test_installation):
        assert test_installation.post_results_to_pr is False
