"""Approval workflow model — configurable multi-step approval chains."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApprovalWorkflow(Base):
    __tablename__ = "approval_workflows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # deal, expense, campaign
    trigger_condition: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g. "value>10000"
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class ApprovalStep(Base):
    __tablename__ = "approval_workflow_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("approval_workflows.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approver_role: Mapped[str] = mapped_column(String(30), nullable=False)  # CEO, ADMIN, MANAGER
    approver_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # specific user
    escalation_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
