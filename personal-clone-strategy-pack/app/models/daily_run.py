from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyRun(Base):
    __tablename__ = "daily_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "run_date", "team_filter", name="uq_daily_runs_org_date_team"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    team_filter: Mapped[str] = mapped_column(String(50), nullable=False, default="*", index=True)
    requested_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed", index=True)
    drafted_plan_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drafted_email_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_approvals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
