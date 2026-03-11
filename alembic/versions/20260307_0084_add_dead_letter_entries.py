"""Add dead_letter_entries table.

Revision ID: 20260307_0084
Revises: 20260307_0083
"""
import sqlalchemy as sa
from alembic import op

revision = "20260307_0084"
down_revision = "20260307_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "dead_letter_entries" not in tables:
        op.create_table(
            "dead_letter_entries",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer,
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("source_type", sa.String(30), nullable=False),
            sa.Column("source_id", sa.String(100), nullable=True),
            sa.Column("source_detail", sa.String(200), nullable=True),
            sa.Column("payload", sa.JSON, default=dict),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column("error_type", sa.String(100), nullable=True),
            sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
            sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column(
                "resolved_by",
                sa.Integer,
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
            sa.Column(
                "resolved_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_dead_letter_org_status",
            "dead_letter_entries",
            ["organization_id", "status"],
        )
        op.create_index(
            "ix_dead_letter_org_source_type",
            "dead_letter_entries",
            ["organization_id", "source_type"],
        )


def downgrade() -> None:
    op.drop_table("dead_letter_entries")
