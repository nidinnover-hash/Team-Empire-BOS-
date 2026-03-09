"""Custom field model — user-defined metadata fields on entities."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ENTITY_TYPES = ("contact", "deal", "task", "project")
FIELD_TYPES = ("text", "number", "date", "boolean", "select")


class CustomFieldDefinition(Base):
    """Defines a custom field (schema) for an entity type."""
    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "entity_type", "field_key", name="uq_custom_field_def"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # contact, deal, task, project
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)  # machine name
    field_label: Mapped[str] = mapped_column(String(200), nullable=False)  # display name
    field_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    options_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # for select type
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )


class CustomFieldValue(Base):
    """Stores actual values for custom fields on specific entities."""
    __tablename__ = "custom_field_values"
    __table_args__ = (
        UniqueConstraint("field_definition_id", "entity_id", name="uq_custom_field_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    field_definition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("custom_field_definitions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
