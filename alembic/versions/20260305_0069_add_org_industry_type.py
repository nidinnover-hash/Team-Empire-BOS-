"""add organization industry_type column

Revision ID: 20260305_0069
Revises: 20260305_0068
"""
from alembic import op
import sqlalchemy as sa

revision = "20260305_0069"
down_revision = "20260305_0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("organizations")}

    if "industry_type" not in existing:
        op.add_column("organizations", sa.Column("industry_type", sa.String(50), nullable=True))

    existing_idxs = {i["name"] for i in inspector.get_indexes("organizations")}
    if "ix_organizations_industry_type" not in existing_idxs:
        op.create_index("ix_organizations_industry_type", "organizations", ["industry_type"])


def downgrade() -> None:
    op.drop_index("ix_organizations_industry_type", table_name="organizations")
    op.drop_column("organizations", "industry_type")
