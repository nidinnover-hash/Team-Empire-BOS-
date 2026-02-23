from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskMetricWeekly(Base):
    __tablename__ = "task_metrics_weekly"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "week_start_date", name="uq_task_metric_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    tasks_assigned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    on_time_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_cycle_time_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class CodeMetricWeekly(Base):
    __tablename__ = "code_metrics_weekly"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "week_start_date", name="uq_code_metric_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    commits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prs_opened: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prs_merged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reviews_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issue_links: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_touched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class CommsMetricWeekly(Base):
    __tablename__ = "comms_metrics_weekly"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "week_start_date", name="uq_comms_metric_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    emails_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    emails_replied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    median_reply_time_minutes: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    escalation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
