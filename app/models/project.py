from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.soft_delete import SoftDeleteMixin


class Project(SoftDeleteMixin, Base):
    """A container that groups related tasks - business or personal."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'paused', 'archived')",
            name="ck_project_status",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_project_progress",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    goal_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("goals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # personal | business | health | finance | other
    category: Mapped[str] = mapped_column(String(50), default="personal")
    # active | completed | paused | archived
    status: Mapped[str] = mapped_column(String(50), default="active")
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
