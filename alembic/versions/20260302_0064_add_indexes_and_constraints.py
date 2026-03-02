"""Add missing indexes and CHECK constraints for performance and data integrity.

Revision ID: 20260302_0064
Revises: 20260302_0063
Create Date: 2026-03-02
"""

from alembic import op

revision = "20260302_0064"
down_revision = "20260302_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Indexes ────────────────────────────────────────────────────────

    # task.depends_on_task_id — FK lookups for dependency queries
    op.create_index(
        "ix_tasks_depends_on_task_id",
        "tasks",
        ["depends_on_task_id"],
    )

    # tasks (organization_id, project_id) — composite for project-scoped queries
    op.create_index(
        "ix_tasks_org_project",
        "tasks",
        ["organization_id", "project_id"],
    )

    # goal.status — frequently filtered for active/completed goals
    op.create_index("ix_goals_status", "goals", ["status"])

    # project.due_date — range queries for upcoming due dates
    op.create_index("ix_projects_due_date", "projects", ["due_date"])

    # ── CHECK constraints ──────────────────────────────────────────────

    # contact.relationship — enforce valid enum values
    op.create_check_constraint(
        "ck_contact_relationship",
        "contacts",
        "relationship IN ('personal', 'business', 'family', 'mentor', 'other')",
    )

    # integration.sync_error_count — must be non-negative
    op.create_check_constraint(
        "ck_integration_sync_error_count_gte0",
        "integrations",
        "sync_error_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_integration_sync_error_count_gte0", "integrations", type_="check")
    op.drop_constraint("ck_contact_relationship", "contacts", type_="check")
    op.drop_index("ix_projects_due_date", table_name="projects")
    op.drop_index("ix_goals_status", table_name="goals")
    op.drop_index("ix_tasks_org_project", table_name="tasks")
    op.drop_index("ix_tasks_depends_on_task_id", table_name="tasks")
