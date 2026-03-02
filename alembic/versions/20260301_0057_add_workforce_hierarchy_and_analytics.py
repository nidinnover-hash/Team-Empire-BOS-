"""Add org hierarchy, departments, lifecycle, and work-pattern analytics tables.

Revision ID: 20260301_0057
Revises: 20260301_0056
Create Date: 2026-03-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260301_0057"
down_revision = "20260301_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("parent_organization_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("country_code", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("branch_label", sa.String(length=120), nullable=True),
    )
    op.create_foreign_key(
        "fk_organizations_parent_organization_id",
        "organizations",
        "organizations",
        ["parent_organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_organizations_parent_organization_id", "organizations", ["parent_organization_id"])
    op.create_index("ix_organizations_country_code", "organizations", ["country_code"])

    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("parent_department_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "name", name="uq_departments_org_name"),
        sa.UniqueConstraint("organization_id", "code", name="uq_departments_org_code"),
    )
    op.create_index("ix_departments_organization_id", "departments", ["organization_id"])
    op.create_index("ix_departments_parent_department_id", "departments", ["parent_department_id"])
    op.create_index("ix_departments_code", "departments", ["code"])
    op.create_index("ix_departments_is_active", "departments", ["is_active"])

    op.add_column("employees", sa.Column("department_id", sa.Integer(), nullable=True))
    op.add_column(
        "employees",
        sa.Column("employment_status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column("employees", sa.Column("hired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("employees", sa.Column("offboarded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_employees_department_id",
        "employees",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_employees_department_id", "employees", ["department_id"])
    op.create_index("ix_employees_employment_status", "employees", ["employment_status"])

    op.create_table(
        "employee_lifecycle_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("checklist_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_employee_lifecycle_events_organization_id", "employee_lifecycle_events", ["organization_id"])
    op.create_index("ix_employee_lifecycle_events_employee_id", "employee_lifecycle_events", ["employee_id"])
    op.create_index("ix_employee_lifecycle_events_event_type", "employee_lifecycle_events", ["event_type"])
    op.create_index("ix_employee_lifecycle_events_actor_user_id", "employee_lifecycle_events", ["actor_user_id"])
    op.create_index("ix_employee_lifecycle_events_created_at", "employee_lifecycle_events", ["created_at"])

    op.create_table(
        "employee_work_patterns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours_logged", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("focus_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meetings_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "employee_id", "work_date", name="uq_work_patterns_org_employee_date"),
    )
    op.create_index("ix_employee_work_patterns_organization_id", "employee_work_patterns", ["organization_id"])
    op.create_index("ix_employee_work_patterns_employee_id", "employee_work_patterns", ["employee_id"])
    op.create_index("ix_employee_work_patterns_work_date", "employee_work_patterns", ["work_date"])
    op.create_index(
        "ix_employee_work_patterns_org_employee_work_date",
        "employee_work_patterns",
        ["organization_id", "employee_id", "work_date"],
    )
    op.create_index(
        "ix_employee_work_patterns_org_work_date",
        "employee_work_patterns",
        ["organization_id", "work_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_employee_work_patterns_org_work_date", table_name="employee_work_patterns")
    op.drop_index("ix_employee_work_patterns_org_employee_work_date", table_name="employee_work_patterns")
    op.drop_index("ix_employee_work_patterns_work_date", table_name="employee_work_patterns")
    op.drop_index("ix_employee_work_patterns_employee_id", table_name="employee_work_patterns")
    op.drop_index("ix_employee_work_patterns_organization_id", table_name="employee_work_patterns")
    op.drop_table("employee_work_patterns")

    op.drop_index("ix_employee_lifecycle_events_created_at", table_name="employee_lifecycle_events")
    op.drop_index("ix_employee_lifecycle_events_actor_user_id", table_name="employee_lifecycle_events")
    op.drop_index("ix_employee_lifecycle_events_event_type", table_name="employee_lifecycle_events")
    op.drop_index("ix_employee_lifecycle_events_employee_id", table_name="employee_lifecycle_events")
    op.drop_index("ix_employee_lifecycle_events_organization_id", table_name="employee_lifecycle_events")
    op.drop_table("employee_lifecycle_events")

    op.drop_index("ix_employees_employment_status", table_name="employees")
    op.drop_index("ix_employees_department_id", table_name="employees")
    op.drop_constraint("fk_employees_department_id", "employees", type_="foreignkey")
    op.drop_column("employees", "offboarded_at")
    op.drop_column("employees", "hired_at")
    op.drop_column("employees", "employment_status")
    op.drop_column("employees", "department_id")

    op.drop_index("ix_departments_is_active", table_name="departments")
    op.drop_index("ix_departments_code", table_name="departments")
    op.drop_index("ix_departments_parent_department_id", table_name="departments")
    op.drop_index("ix_departments_organization_id", table_name="departments")
    op.drop_table("departments")

    op.drop_index("ix_organizations_country_code", table_name="organizations")
    op.drop_index("ix_organizations_parent_organization_id", table_name="organizations")
    op.drop_constraint("fk_organizations_parent_organization_id", "organizations", type_="foreignkey")
    op.drop_column("organizations", "branch_label")
    op.drop_column("organizations", "country_code")
    op.drop_column("organizations", "parent_organization_id")
