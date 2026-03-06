"""Add account security columns to users table.

Adds failed_login_count, locked_until, and last_activity_at for per-account
lockout and idle session tracking.

Revision ID: 20260306_0081
Revises: 20260306_0080
"""
import sqlalchemy as sa
from alembic import op

revision: str = "20260306_0081"
down_revision: str | None = "20260306_0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("locked_until")
        batch_op.drop_column("failed_login_count")
