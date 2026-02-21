from datetime import datetime, timezone, date
from sqlalchemy import String, Text, Boolean, DateTime, Integer, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Task(Base):
    """A to-do item with priority, category, and optional project link."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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
