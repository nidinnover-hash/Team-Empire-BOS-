"""Add recruitment_placements table (EmpireO).

Revision ID: 20260312_0089
Revises: 20260311_0088
Create Date: 2026-03-12

"""
from alembic import op
import sqlalchemy as sa

revision = "20260312_0089"
down_revision = "20260311_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recruitment_placements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.String(255), nullable=False),
        sa.Column("job_id", sa.String(255), nullable=True),
        sa.Column("approval_id", sa.Integer(), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_date", sa.String(50), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recruitment_placements_organization_id", "recruitment_placements", ["organization_id"])
    op.create_index("ix_recruitment_placements_candidate_id", "recruitment_placements", ["candidate_id"])
    op.create_index("ix_recruitment_placements_job_id", "recruitment_placements", ["job_id"])
    op.create_index("ix_recruitment_placements_approval_id", "recruitment_placements", ["approval_id"])


def downgrade() -> None:
    op.drop_index("ix_recruitment_placements_approval_id", table_name="recruitment_placements")
    op.drop_index("ix_recruitment_placements_job_id", table_name="recruitment_placements")
    op.drop_index("ix_recruitment_placements_candidate_id", table_name="recruitment_placements")
    op.drop_index("ix_recruitment_placements_organization_id", table_name="recruitment_placements")
    op.drop_table("recruitment_placements")
