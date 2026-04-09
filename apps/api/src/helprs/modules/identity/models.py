"""User identity ORM models."""

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from helprs.core.database import Base


class GitHubUser(Base):
    """GitHub-authenticated user identity."""

    __tablename__ = "github_users"

    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    github_login: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    github_access_token_enc: Mapped[str] = mapped_column(String(512), nullable=False)
