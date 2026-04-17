"""Tests for container session models and status transitions."""

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
        assert statuses == {"pending", "running", "completed", "failed", "timeout"}


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
