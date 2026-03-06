"""Add signature and prev_hash columns to events table for audit chain integrity.

Revision ID: 20260306_0080
Revises: 20260306_0079
"""
import sqlalchemy as sa
from alembic import op

revision: str = "20260306_0080"
down_revision: str | None = "20260306_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(sa.Column("signature", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("prev_hash", sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_column("prev_hash")
        batch_op.drop_column("signature")
