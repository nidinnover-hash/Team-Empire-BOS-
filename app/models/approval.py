from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "status != 'approved' OR approved_by IS NOT NULL",
            name="ck_approval_approved_has_user",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_approval_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        default=1,
        index=True,
    )
    requested_by: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    approval_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

