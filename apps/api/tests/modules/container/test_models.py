"""Tests for container session models and status transitions."""

from sqlalchemy.dialects import postgresql

from helprs.modules.container.models import ContainerSession, ContainerStatus


class TestContainerStatus:
    def test_status_values(self):
        assert ContainerStatus.PENDING.value == "pending"
        assert ContainerStatus.RUNNING.value == "running"
        assert ContainerStatus.COMPLETED.value == "completed"
        assert ContainerStatus.FAILED.value == "failed"
        assert ContainerStatus.TIMEOUT.value == "timeout"

    def test_status_is_str_enum(self):
        assert isinstance(ContainerStatus.PENDING, str)
        assert ContainerStatus.PENDING == "pending"

    def test_all_statuses_exist(self):
        statuses = {s.value for s in ContainerStatus}
        assert statuses == {"pending", "running", "completed", "failed", "timeout", "cancelled"}

    def test_cancelled_is_distinct_from_completed(self):
        """A user-requested stop must not be counted as a successful run."""
        assert ContainerStatus.CANCELLED != ContainerStatus.COMPLETED


class TestStatusPersistenceForm:
    """The column stores enum VALUES, matching server_default and the API.

    SQLAlchemy's Enum persists the member NAME unless told otherwise, so this
    used to write "RUNNING" while the migration's server_default was "pending"
    and the API returned "running". A row created without an explicit status
    was then permanently unreadable through the ORM.
    """

    def _processors(self):
        column = ContainerSession.__table__.c.status
        dialect = postgresql.dialect()
        return column.type.bind_processor(dialect), column.type.result_processor(dialect, None)

    def test_every_member_is_stored_as_its_value(self):
        to_db, _ = self._processors()
        for member in ContainerStatus:
            assert to_db(member) == member.value

    def test_a_server_defaulted_row_is_readable(self):
        """'pending' is what the DB default writes; reading it must not raise."""
        _, from_db = self._processors()
        assert from_db("pending") is ContainerStatus.PENDING

    def test_every_stored_value_round_trips(self):
        to_db, from_db = self._processors()
        for member in ContainerStatus:
            assert from_db(to_db(member)) is member


class TestContainerSessionModel:
    def test_tablename(self):
        assert ContainerSession.__tablename__ == "container_sessions"

    def test_model_has_expected_columns(self):
        column_names = {c.name for c in ContainerSession.__table__.columns}
        expected = {
            "id",
            "installation_id",
            "user_id",
            "pr_number",
            "repo_full_name",
            "skill_name",
            "container_id",
            "status",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(column_names)

    def test_status_column_default(self):
        col = ContainerSession.__table__.c.status
        assert col.default.arg == ContainerStatus.PENDING

    def test_container_id_nullable(self):
        col = ContainerSession.__table__.c.container_id
        assert col.nullable is True

    def test_user_id_nullable(self):
        col = ContainerSession.__table__.c.user_id
        assert col.nullable is True

    def test_installation_id_not_nullable(self):
        col = ContainerSession.__table__.c.installation_id
        assert col.nullable is False
