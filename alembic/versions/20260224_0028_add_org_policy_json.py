"""add org policy json

Revision ID: 20260224_0028
Revises: 20260224_0027
Create Date: 2026-02-24 22:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260224_0028"
down_revision = "20260224_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("policy_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.alter_column("organizations", "policy_json", server_default=None)


def downgrade() -> None:
    op.drop_column("organizations", "policy_json")

