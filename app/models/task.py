from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class Task(Base):
    """A to-do item with priority, category, and optional project link."""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("organization_id", "external_source", "external_id", name="uq_task_external"),
        CheckConstraint(
            "category IN ('personal', 'business', 'health', 'finance', 'other')",
            name="ck_task_category",
        ),
        CheckConstraint(
            "priority >= 1 AND priority <= 4",
            name="ck_task_priority",
        ),
        CheckConstraint(
            "NOT is_done OR completed_at IS NOT NULL",
            name="ck_task_done_has_completed_at",
        ),
        Index("ix_tasks_org_project", "organization_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 1=low  2=medium  3=high  4=urgent
    priority: Mapped[int] = mapped_column(Integer, default=2, index=True)
    # personal | business | health | finance | other
    category: Mapped[str] = mapped_column(String(50), default="personal")
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    depends_on_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    external_source: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} done={self.is_done}>"
