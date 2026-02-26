from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClonePerformanceWeekly(Base):
    __tablename__ = "clone_performance_weekly"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "employee_id",
            "week_start_date",
            name="uq_clone_perf_week",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    productivity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    collaboration_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    learning_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    readiness_level: Mapped[str] = mapped_column(String(20), nullable=False, default="developing")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
