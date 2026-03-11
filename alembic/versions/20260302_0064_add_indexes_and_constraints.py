"""Add missing indexes and CHECK constraints for performance and data integrity.

Revision ID: 20260302_0064
Revises: 20260302_0063
Create Date: 2026-03-02
"""

import sqlalchemy as sa
from alembic import op

revision = "20260302_0064"
down_revision = "20260302_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── Indexes ────────────────────────────────────────────────────────

    # task.depends_on_task_id — FK lookups for dependency queries
    existing_tasks = {i["name"] for i in inspector.get_indexes("tasks")}
    if "ix_tasks_depends_on_task_id" not in existing_tasks:
        op.create_index(
            "ix_tasks_depends_on_task_id",
            "tasks",
            ["depends_on_task_id"],
        )

    # tasks (organization_id, project_id) — composite for project-scoped queries
    if "ix_tasks_org_project" not in existing_tasks:
        op.create_index(
            "ix_tasks_org_project",
            "tasks",
            ["organization_id", "project_id"],
        )

    # goal.status — frequently filtered for active/completed goals
    existing_goals = {i["name"] for i in inspector.get_indexes("goals")}
    if "ix_goals_status" not in existing_goals:
        op.create_index("ix_goals_status", "goals", ["status"])

    # project.due_date — range queries for upcoming due dates
    existing_proj = {i["name"] for i in inspector.get_indexes("projects")}
    if "ix_projects_due_date" not in existing_proj:
        op.create_index("ix_projects_due_date", "projects", ["due_date"])

    # ── CHECK constraints ──────────────────────────────────────────────

    # contact.relationship — enforce valid enum values
    try:
        op.create_check_constraint(
            "ck_contact_relationship",
            "contacts",
            "relationship IN ('personal', 'business', 'family', 'mentor', 'other')",
        )
    except Exception:
        pass

    # integration.sync_error_count — must be non-negative
    try:
        op.create_check_constraint(
            "ck_integration_sync_error_count_gte0",
            "integrations",
            "sync_error_count >= 0",
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_constraint("ck_integration_sync_error_count_gte0", "integrations", type_="check")
    op.drop_constraint("ck_contact_relationship", "contacts", type_="check")
    op.drop_index("ix_projects_due_date", table_name="projects")
    op.drop_index("ix_goals_status", table_name="goals")
    op.drop_index("ix_tasks_org_project", table_name="tasks")
    op.drop_index("ix_tasks_depends_on_task_id", table_name="tasks")
