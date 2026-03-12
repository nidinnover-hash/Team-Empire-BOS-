"""Add study_abroad_applications, milestone_templates, application_steps.

Revision ID: 20260312_0091
Revises: 20260312_0090
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20260312_0091"
down_revision = "20260312_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_abroad_applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("external_application_id", sa.String(255), nullable=False),
        sa.Column("program_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="in_progress"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_study_abroad_applications_organization_id", "study_abroad_applications", ["organization_id"])
    op.create_index("ix_study_abroad_applications_external_application_id", "study_abroad_applications", ["external_application_id"])

    op.create_table(
        "study_abroad_milestone_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.String(255), nullable=False),
        sa.Column("step_key", sa.String(100), nullable=False),
        sa.Column("step_name", sa.String(255), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("days_before_deadline", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_study_abroad_milestone_templates_organization_id", "study_abroad_milestone_templates", ["organization_id"])
    op.create_index("ix_study_abroad_milestone_templates_program_id", "study_abroad_milestone_templates", ["program_id"])

    op.create_table(
        "study_abroad_application_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(100), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["study_abroad_applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_study_abroad_application_steps_application_id", "study_abroad_application_steps", ["application_id"])
    op.create_index("ix_study_abroad_application_steps_step_key", "study_abroad_application_steps", ["step_key"])


def downgrade() -> None:
    op.drop_index("ix_study_abroad_application_steps_step_key", table_name="study_abroad_application_steps")
    op.drop_index("ix_study_abroad_application_steps_application_id", table_name="study_abroad_application_steps")
    op.drop_table("study_abroad_application_steps")
    op.drop_index("ix_study_abroad_milestone_templates_program_id", table_name="study_abroad_milestone_templates")
    op.drop_index("ix_study_abroad_milestone_templates_organization_id", table_name="study_abroad_milestone_templates")
    op.drop_table("study_abroad_milestone_templates")
    op.drop_index("ix_study_abroad_applications_external_application_id", table_name="study_abroad_applications")
    op.drop_index("ix_study_abroad_applications_organization_id", table_name="study_abroad_applications")
    op.drop_table("study_abroad_applications")
