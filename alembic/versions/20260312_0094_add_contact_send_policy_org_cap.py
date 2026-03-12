"""Add max_org_sends_per_day to contact_send_policies (org-level rate cap).

Revision ID: 20260312_0094
Revises: 20260312_0093
Create Date: 2026-03-12

"""
from alembic import op
import sqlalchemy as sa

revision = "20260312_0094"
down_revision = "20260312_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contact_send_policies",
        sa.Column("max_org_sends_per_day", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contact_send_policies", "max_org_sends_per_day")
