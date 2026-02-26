import datetime as dt

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyTaskPlan(Base):
    """
    AI-generated daily task plan for one team member.
    Status flow: draft → approved → sent
    Nothing reaches the employee until Nidin approves.
    """
    __tablename__ = "daily_task_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'sent')",
            name="ck_daily_task_plan_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    team_member_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("team_members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    tasks_json: Mapped[list] = mapped_column(JSON, default=list)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.UTC),
    )
