from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntegrationSignal(Base):
    __tablename__ = "integration_signals"
    __table_args__ = (
        UniqueConstraint("organization_id", "source", "external_id", name="uq_signal_org_source_ext"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # clickup/github/gmail
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of payload
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
