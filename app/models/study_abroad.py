"""Study abroad (ESA) — applications and milestones. BOS is the control plane."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StudyAbroadApplication(Base):
    __tablename__ = "study_abroad_applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    external_application_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    program_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="in_progress")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


class StudyAbroadMilestoneTemplate(Base):
    __tablename__ = "study_abroad_milestone_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    program_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    days_before_deadline: Mapped[int | None] = mapped_column(Integer, nullable=True)


class StudyAbroadApplicationStep(Base):
    __tablename__ = "study_abroad_application_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("study_abroad_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
