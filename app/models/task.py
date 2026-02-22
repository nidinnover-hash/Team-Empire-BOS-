from datetime import datetime, timezone, date
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Task(Base):
    """A to-do item with priority, category, and optional project link."""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "external_source", "external_id", name="uq_task_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 1=low  2=medium  3=high  4=urgent
    priority: Mapped[int] = mapped_column(Integer, default=2)
    # personal | business | health | finance | other
    category: Mapped[str] = mapped_column(String(50), default="personal")
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    external_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
