"""add users.is_super_admin column

Revision ID: 20260305_0076
Revises: 20260305_0071
"""
import sqlalchemy as sa
from alembic import op

revision = "20260305_0076"
down_revision = "20260305_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "is_super_admin" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "is_super_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("users")}
    if "is_super_admin" in columns:
        op.drop_column("users", "is_super_admin")
