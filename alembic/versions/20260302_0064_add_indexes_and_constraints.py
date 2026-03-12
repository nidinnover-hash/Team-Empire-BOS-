"""Add missing indexes and CHECK constraints for performance and data integrity.

Revision ID: 20260302_0064
Revises: 20260302_0063
Create Date: 2026-03-02
"""

import sqlalchemy as sa
from sqlalchemy.exc import NoSuchTableError

from alembic import op

revision = "20260302_0064"
down_revision = "20260302_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _get_indexes(table_name: str) -> set[str]:
        try:
            return {i["name"] for i in inspector.get_indexes(table_name)}
        except NoSuchTableError:
            return set()

    # ── Indexes ────────────────────────────────────────────────────────

    # task.depends_on_task_id — FK lookups for dependency queries
    if inspector.has_table("tasks"):
        existing_tasks = _get_indexes("tasks")
        if "ix_tasks_depends_on_task_id" not in existing_tasks:
            op.create_index("ix_tasks_depends_on_task_id", "tasks", ["depends_on_task_id"])
        if "ix_tasks_org_project" not in existing_tasks:
            op.create_index("ix_tasks_org_project", "tasks", ["organization_id", "project_id"])

    # goal.status — frequently filtered for active/completed goals
    if inspector.has_table("goals"):
        existing_goals = _get_indexes("goals")
        if "ix_goals_status" not in existing_goals:
            op.create_index("ix_goals_status", "goals", ["status"])

    # project.due_date — range queries for upcoming due dates
    if inspector.has_table("projects"):
        existing_proj = _get_indexes("projects")
        if "ix_projects_due_date" not in existing_proj:
            op.create_index("ix_projects_due_date", "projects", ["due_date"])

    # ── CHECK constraints ──────────────────────────────────────────────

    # contact.relationship — enforce valid enum values
    existing_ck = {
        row[0] for row in bind.execute(sa.text("SELECT conname FROM pg_constraint")).fetchall()
    }
    if "ck_contact_relationship" not in existing_ck:
        op.create_check_constraint(
            "ck_contact_relationship",
            "contacts",
            "relationship IN ('personal', 'business', 'family', 'mentor', 'other')",
        )

    # integration.sync_error_count — must be non-negative
    if "ck_integration_sync_error_count_gte0" not in existing_ck:
        op.create_check_constraint(
            "ck_integration_sync_error_count_gte0",
            "integrations",
            "sync_error_count >= 0",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_ck = {
        row[0] for row in bind.execute(sa.text("SELECT conname FROM pg_constraint")).fetchall()
    }
    if "ck_integration_sync_error_count_gte0" in existing_ck and inspector.has_table("integrations"):
        op.drop_constraint("ck_integration_sync_error_count_gte0", "integrations", type_="check")
    if "ck_contact_relationship" in existing_ck and inspector.has_table("contacts"):
        op.drop_constraint("ck_contact_relationship", "contacts", type_="check")

    if inspector.has_table("projects"):
        existing_proj = {i["name"] for i in inspector.get_indexes("projects")}
        if "ix_projects_due_date" in existing_proj:
            op.drop_index("ix_projects_due_date", table_name="projects")
    if inspector.has_table("goals"):
        existing_goals = {i["name"] for i in inspector.get_indexes("goals")}
        if "ix_goals_status" in existing_goals:
            op.drop_index("ix_goals_status", table_name="goals")
    if inspector.has_table("tasks"):
        existing_tasks = {i["name"] for i in inspector.get_indexes("tasks")}
        if "ix_tasks_org_project" in existing_tasks:
            op.drop_index("ix_tasks_org_project", table_name="tasks")
        if "ix_tasks_depends_on_task_id" in existing_tasks:
            op.drop_index("ix_tasks_depends_on_task_id", table_name="tasks")
