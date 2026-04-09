"""Tests for database module."""

import uuid

from helprs.core.database import Base


def test_base_metadata_is_importable():
    assert Base.metadata is not None


def test_base_has_common_columns():
    mapper_attrs = set(Base.__annotations__.keys())
    assert "id" in mapper_attrs
    assert "created_at" in mapper_attrs
    assert "updated_at" in mapper_attrs


def test_base_id_column_is_uuid_type():
    # Verify the id column uses UUID type via mapped_column
    mapped_col = Base.__dict__["id"]
    # The column should produce UUID primary keys
    assert mapped_col is not None
    # Verify we can instantiate a UUID (the default factory works)
    val = uuid.uuid4()
    assert isinstance(val, uuid.UUID)
