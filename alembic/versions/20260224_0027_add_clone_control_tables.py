"""Add clone control tables for identity, profile, feedback, and training plans.

Revision ID: 20260224_0027
Revises: 20260224_0026
Create Date: 2026-02-24 22:40:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260224_0027"
down_revision: str | None = "20260224_0026"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "employee_identity_map" not in tables:
        op.create_table(
            "employee_identity_map",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("work_email", sa.String(length=320), nullable=True),
            sa.Column("github_login", sa.String(length=255), nullable=True),
            sa.Column("clickup_user_id", sa.String(length=100), nullable=True),
            sa.Column("slack_user_id", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "employee_id", name="uq_identity_org_employee"),
        )
        op.create_index("ix_employee_identity_map_organization_id", "employee_identity_map", ["organization_id"], unique=False)
        op.create_index("ix_employee_identity_map_employee_id", "employee_identity_map", ["employee_id"], unique=False)
        op.create_index("ix_employee_identity_map_work_email", "employee_identity_map", ["work_email"], unique=False)
        op.create_index("ix_employee_identity_map_github_login", "employee_identity_map", ["github_login"], unique=False)
        op.create_index("ix_employee_identity_map_clickup_user_id", "employee_identity_map", ["clickup_user_id"], unique=False)
        op.create_index("ix_employee_identity_map_slack_user_id", "employee_identity_map", ["slack_user_id"], unique=False)

    if "employee_clone_profiles" not in tables:
        op.create_table(
            "employee_clone_profiles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("strengths_json", sa.Text(), nullable=False),
            sa.Column("weak_zones_json", sa.Text(), nullable=False),
            sa.Column("preferred_task_types_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "employee_id", name="uq_clone_profile_org_employee"),
        )
        op.create_index("ix_employee_clone_profiles_organization_id", "employee_clone_profiles", ["organization_id"], unique=False)
        op.create_index("ix_employee_clone_profiles_employee_id", "employee_clone_profiles", ["employee_id"], unique=False)

    if "clone_learning_feedback" not in tables:
        op.create_table(
            "clone_learning_feedback",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("source_type", sa.String(length=30), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("outcome_score", sa.Float(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_clone_learning_feedback_organization_id", "clone_learning_feedback", ["organization_id"], unique=False)
        op.create_index("ix_clone_learning_feedback_employee_id", "clone_learning_feedback", ["employee_id"], unique=False)
        op.create_index("ix_clone_learning_feedback_source_type", "clone_learning_feedback", ["source_type"], unique=False)
        op.create_index("ix_clone_learning_feedback_source_id", "clone_learning_feedback", ["source_id"], unique=False)
        op.create_index("ix_clone_learning_feedback_created_at", "clone_learning_feedback", ["created_at"], unique=False)

    if "role_training_plans" not in tables:
        op.create_table(
            "role_training_plans",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("week_start_date", sa.Date(), nullable=False),
            sa.Column("role_focus", sa.String(length=100), nullable=False),
            sa.Column("plan_markdown", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "employee_id", "week_start_date", name="uq_role_training_week"),
        )
        op.create_index("ix_role_training_plans_organization_id", "role_training_plans", ["organization_id"], unique=False)
        op.create_index("ix_role_training_plans_employee_id", "role_training_plans", ["employee_id"], unique=False)
        op.create_index("ix_role_training_plans_week_start_date", "role_training_plans", ["week_start_date"], unique=False)
        op.create_index("ix_role_training_plans_status", "role_training_plans", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_role_training_plans_status", table_name="role_training_plans")
    op.drop_index("ix_role_training_plans_week_start_date", table_name="role_training_plans")
    op.drop_index("ix_role_training_plans_employee_id", table_name="role_training_plans")
    op.drop_index("ix_role_training_plans_organization_id", table_name="role_training_plans")
    op.drop_table("role_training_plans")

    op.drop_index("ix_clone_learning_feedback_created_at", table_name="clone_learning_feedback")
    op.drop_index("ix_clone_learning_feedback_source_id", table_name="clone_learning_feedback")
    op.drop_index("ix_clone_learning_feedback_source_type", table_name="clone_learning_feedback")
    op.drop_index("ix_clone_learning_feedback_employee_id", table_name="clone_learning_feedback")
    op.drop_index("ix_clone_learning_feedback_organization_id", table_name="clone_learning_feedback")
    op.drop_table("clone_learning_feedback")

    op.drop_index("ix_employee_clone_profiles_employee_id", table_name="employee_clone_profiles")
    op.drop_index("ix_employee_clone_profiles_organization_id", table_name="employee_clone_profiles")
    op.drop_table("employee_clone_profiles")

    op.drop_index("ix_employee_identity_map_slack_user_id", table_name="employee_identity_map")
    op.drop_index("ix_employee_identity_map_clickup_user_id", table_name="employee_identity_map")
    op.drop_index("ix_employee_identity_map_github_login", table_name="employee_identity_map")
    op.drop_index("ix_employee_identity_map_work_email", table_name="employee_identity_map")
    op.drop_index("ix_employee_identity_map_employee_id", table_name="employee_identity_map")
    op.drop_index("ix_employee_identity_map_organization_id", table_name="employee_identity_map")
    op.drop_table("employee_identity_map")
