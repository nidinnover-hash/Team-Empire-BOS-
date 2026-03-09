"""Import/export preset model — saved column mappings and configurations."""
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportExportPreset(Base):
    __tablename__ = "import_export_presets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # import, export
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # contact, deal, task
    column_mapping_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # extra options
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC),
    )
