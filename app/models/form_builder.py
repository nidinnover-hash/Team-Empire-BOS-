"""Form builder model — web forms with fields and submissions."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FormDefinition(Base):
    __tablename__ = "form_definitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # [{name, type, required, options}]
    redirect_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confirmation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    total_submissions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class FormSubmission(Base):
    __tablename__ = "form_submissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    form_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("form_definitions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    contact_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # linked contact if matched
    source_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
