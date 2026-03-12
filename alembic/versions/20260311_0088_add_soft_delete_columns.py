"""Add soft delete columns (is_deleted, deleted_at) to Contact, Task, Deal, Goal, Project.

Revision ID: 20260311_0088
Revises: 20260310_0087
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa

revision = "20260311_0088"
down_revision = "20260310_0087"
branch_labels = None
depends_on = None

_TABLES = ("contacts", "tasks", "deals", "goals", "projects")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in _TABLES:
        existing = {c["name"] for c in inspector.get_columns(table)}
        if "is_deleted" not in existing:
            op.add_column(table, sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"))
        if "deleted_at" not in existing:
            op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        existing_idxs = {i["name"] for i in inspector.get_indexes(table)}
        if f"ix_{table}_is_deleted" not in existing_idxs:
            op.create_index(f"ix_{table}_is_deleted", table, ["is_deleted"])


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_is_deleted", table_name=table)
        op.drop_column(table, "deleted_at")
        op.drop_column(table, "is_deleted")
