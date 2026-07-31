"""Tests for suppression labels.

Validation lives in ``SuppressionLabelsRequest`` (it runs before any handler
is entered), so the rules are tested against the schema and persistence
against the use case — one rule, one place.
"""

import pytest
from pydantic import ValidationError

from helprs.core.exceptions import NotFoundError
from helprs.modules.installation.schemas import SuppressionLabelsRequest
from helprs.modules.installation.service import update_suppression_labels


class TestSuppressionLabelsRequest:
    def test_accepts_valid_labels(self):
        assert SuppressionLabelsRequest(labels=["hotfix", "wip"]).labels == ["hotfix", "wip"]

    def test_strips_and_deduplicates_preserving_order(self):
        assert SuppressionLabelsRequest(labels=[" hotfix ", "wip", "hotfix"]).labels == ["hotfix", "wip"]

    def test_rejects_more_than_twenty(self):
        with pytest.raises(ValidationError, match="Maximum 20"):
            SuppressionLabelsRequest(labels=[f"label-{i}" for i in range(21)])

    def test_rejects_overlong_label(self):
        with pytest.raises(ValidationError, match="exceeds maximum 50"):
            SuppressionLabelsRequest(labels=["a" * 51])

    def test_rejects_invalid_characters(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            SuppressionLabelsRequest(labels=["invalid label!"])

    def test_accepts_empty_list(self):
        assert SuppressionLabelsRequest(labels=[]).labels == []


class TestUpdateSuppressionLabels:
    async def test_persists_labels(self, db_session, test_installation):
        result = await update_suppression_labels(db_session, test_installation.id, ["hotfix", "wip"])

        assert result.suppression_labels == ["hotfix", "wip"]

    async def test_clearing_labels_persists_empty_list(self, db_session, test_installation):
        await update_suppression_labels(db_session, test_installation.id, ["hotfix"])

        result = await update_suppression_labels(db_session, test_installation.id, [])

        assert result.suppression_labels == []

    async def test_unknown_installation_is_not_found(self, db_session):
        import uuid

        with pytest.raises(NotFoundError):
            await update_suppression_labels(db_session, uuid.uuid4(), ["hotfix"])
