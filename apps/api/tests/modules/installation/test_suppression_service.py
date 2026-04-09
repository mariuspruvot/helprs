"""Unit tests for suppression labels service."""

import pytest

from helprs.core.exceptions import DomainValidationError
from helprs.modules.installation.service import (
    get_default_suppression_labels,
    update_suppression_labels,
)


class TestGetDefaultSuppressionLabels:
    def test_returns_defaults(self):
        labels = get_default_suppression_labels()
        assert labels == ["hotfix", "urgent", "trivial"]


class TestUpdateSuppressionLabels:
    async def test_success(self, db_session, test_installation):
        result = await update_suppression_labels(
            db_session, test_installation.id, ["hotfix", "wip"]
        )
        assert result.suppression_labels == ["hotfix", "wip"]

    async def test_too_many_labels(self, db_session, test_installation):
        labels = [f"label-{i}" for i in range(21)]
        with pytest.raises(DomainValidationError, match="Maximum 20"):
            await update_suppression_labels(db_session, test_installation.id, labels)

    async def test_label_too_long(self, db_session, test_installation):
        labels = ["a" * 51]
        with pytest.raises(DomainValidationError, match="exceeds maximum length"):
            await update_suppression_labels(db_session, test_installation.id, labels)

    async def test_invalid_chars(self, db_session, test_installation):
        labels = ["invalid label!"]
        with pytest.raises(DomainValidationError, match="invalid characters"):
            await update_suppression_labels(db_session, test_installation.id, labels)

    async def test_empty_list(self, db_session, test_installation):
        result = await update_suppression_labels(
            db_session, test_installation.id, []
        )
        assert result.suppression_labels == []
