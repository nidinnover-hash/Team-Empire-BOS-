"""Document template model — proposals/contracts with merge fields."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)  # proposal, contract, invoice, letter
    content: Mapped[str] = mapped_column(Text, nullable=False)
    merge_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # available {{fields}}
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
