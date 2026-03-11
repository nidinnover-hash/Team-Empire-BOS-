"""Add source column to notes for integration dedup.

Revision ID: 20260228_0052
Revises: 20260227_0051
Create Date: 2026-02-28
"""
import sqlalchemy as sa
from alembic import op

revision = "20260228_0052"
down_revision = "20260227_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("notes")}

    if "source" not in existing:
        op.add_column(
            "notes",
            sa.Column("source", sa.String(50), nullable=True),
        )

    existing_idxs = {i["name"] for i in inspector.get_indexes("notes")}
    if "ix_notes_source" not in existing_idxs:
        op.create_index("ix_notes_source", "notes", ["source"])


def downgrade() -> None:
    op.drop_index("ix_notes_source", table_name="notes")
    op.drop_column("notes", "source")
