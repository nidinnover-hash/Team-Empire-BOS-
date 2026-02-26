import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProfileMemory(Base):
    """Key-value store for Nidin's identity, business rules, goals, and preferences."""
    __tablename__ = "profile_memory"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_profile_memory_org_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
        onupdate=lambda: dt.datetime.now(dt.UTC),
    )


class TeamMember(Base):
    """Your actual team — separate from the generic users/auth table."""
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    team: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    reports_to_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("team_members.id", ondelete="SET NULL"),
        nullable=True,
    )
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1=none → 5=expert
    current_project: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
    )


class DailyContext(Base):
    """Short-term memory — today's priorities, meetings, blockers, decisions."""
    __tablename__ = "daily_context"
    __table_args__ = (
        Index("ix_daily_context_org_date", "organization_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    context_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    related_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
    )


class AvatarMemory(Base):
    """Strict avatar-scoped memory store to prevent personal/professional cross-leakage."""
    __tablename__ = "avatar_memory"
    __table_args__ = (
        UniqueConstraint("organization_id", "avatar_mode", "key", name="uq_avatar_memory_org_mode_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    avatar_mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
        index=True,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
        onupdate=lambda: dt.datetime.now(dt.UTC),
        index=True,
    )
