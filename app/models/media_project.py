from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MediaProject(Base):
    """Video/audio/podcast editing project tracker."""
    __tablename__ = "media_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(30), nullable=False, default="youtube")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    script_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    quality_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    feedback_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
