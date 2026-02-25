from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SocialPost(Base):
    __tablename__ = "social_posts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'queued', 'approved', 'published', 'failed')",
            name="ck_social_post_status",
        ),
        CheckConstraint(
            "content_mode IN ('social_media', 'entertainment')",
            name="ck_social_post_content_mode",
        ),
        CheckConstraint(
            "("
            "(content_mode = 'social_media' AND platform IN ('instagram','facebook','linkedin','x','tiktok','other'))"
            " OR "
            "(content_mode = 'entertainment' AND platform IN ('youtube','audible'))"
            ")",
            name="ck_social_post_mode_platform",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    content_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="social_media", index=True)
    platform: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    media_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )
