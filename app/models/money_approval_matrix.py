"""Money approval matrix — who can approve by action_type and amount band."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MoneyApprovalMatrix(Base):
    __tablename__ = "money_approval_matrices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    amount_min: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    amount_max: Mapped[float] = mapped_column(Float, nullable=False, default=999999999)
    allowed_roles: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # e.g. ["MANAGER", "ADMIN"]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
