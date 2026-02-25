"""Create CEO control and compliance snapshot tables.

Revision ID: 0020
Revises: 0019
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    existing_org_people_indexes = {
        idx["name"] for idx in inspector.get_indexes("org_people")
    } if "org_people" in tables else set()

    if "org_people" not in tables:
        op.create_table(
            "org_people",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("internal_role", sa.String(50), nullable=False),
            sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("manager_email", sa.String(320), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if "ix_org_people_org_id" not in existing_org_people_indexes:
        op.create_index("ix_org_people_org_id", "org_people", ["organization_id"])
    if "ix_org_people_email" not in existing_org_people_indexes:
        op.create_index("ix_org_people_email", "org_people", ["email"])
    if "uq_org_people_org_email" not in existing_org_people_indexes:
        # SQLite does not support ALTER TABLE ADD CONSTRAINT UNIQUE.
        op.create_index("uq_org_people_org_email", "org_people", ["organization_id", "email"], unique=True)

    existing_gh_identity_indexes = {
        idx["name"] for idx in inspector.get_indexes("github_identity_map")
    } if "github_identity_map" in tables else set()
    if "github_identity_map" not in tables:
        op.create_table(
            "github_identity_map",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("company_email", sa.String(320), nullable=False),
            sa.Column("github_login", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if "ix_github_identity_map_org_id" not in existing_gh_identity_indexes:
        op.create_index("ix_github_identity_map_org_id", "github_identity_map", ["organization_id"])
    if "ix_github_identity_map_email" not in existing_gh_identity_indexes:
        op.create_index("ix_github_identity_map_email", "github_identity_map", ["company_email"])
    if "ix_github_identity_map_login" not in existing_gh_identity_indexes:
        op.create_index("ix_github_identity_map_login", "github_identity_map", ["github_login"])
    if "uq_github_identity_map_org_email" not in existing_gh_identity_indexes:
        # SQLite does not support ALTER TABLE ADD CONSTRAINT UNIQUE.
        op.create_index(
            "uq_github_identity_map_org_email",
            "github_identity_map",
            ["organization_id", "company_email"],
            unique=True,
        )

    op.create_table(
        "github_role_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("org_login", sa.String(255), nullable=False),
        sa.Column("github_login", sa.String(255), nullable=False),
        sa.Column("org_role", sa.String(50), nullable=True),
        sa.Column("repo_name", sa.String(255), nullable=True),
        sa.Column("repo_permission", sa.String(50), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gh_role_snapshot_org_id", "github_role_snapshot", ["organization_id"])
    op.create_index("ix_gh_role_snapshot_login", "github_role_snapshot", ["github_login"])
    op.create_index("ix_gh_role_snapshot_repo", "github_role_snapshot", ["repo_name"])
    op.create_index("ix_gh_role_snapshot_synced", "github_role_snapshot", ["synced_at"])

    op.create_table(
        "github_repo_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("repo_name", sa.String(255), nullable=False),
        sa.Column("default_branch", sa.String(120), nullable=True),
        sa.Column("is_protected", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("requires_reviews", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("required_checks_enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gh_repo_snapshot_org_id", "github_repo_snapshot", ["organization_id"])
    op.create_index("ix_gh_repo_snapshot_repo", "github_repo_snapshot", ["repo_name"])
    op.create_index("ix_gh_repo_snapshot_synced", "github_repo_snapshot", ["synced_at"])

    op.create_table(
        "github_pr_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("repo_name", sa.String(255), nullable=False),
        sa.Column("pr_number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("requested_reviewers", sa.Text, nullable=False, server_default="[]"),
        sa.Column("created_at_remote", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_remote", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checks_state", sa.String(50), nullable=True),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gh_pr_snapshot_org_id", "github_pr_snapshot", ["organization_id"])
    op.create_index("ix_gh_pr_snapshot_repo", "github_pr_snapshot", ["repo_name"])
    op.create_index("ix_gh_pr_snapshot_author", "github_pr_snapshot", ["author"])
    op.create_index("ix_gh_pr_snapshot_synced", "github_pr_snapshot", ["synced_at"])

    op.create_table(
        "clickup_spaces",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clickup_spaces_org_id", "clickup_spaces", ["organization_id"])
    op.create_index("ix_clickup_spaces_ext", "clickup_spaces", ["external_id"])

    op.create_table(
        "clickup_folders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("space_external_id", sa.String(100), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clickup_folders_org_id", "clickup_folders", ["organization_id"])
    op.create_index("ix_clickup_folders_ext", "clickup_folders", ["external_id"])

    op.create_table(
        "clickup_lists",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("folder_external_id", sa.String(100), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clickup_lists_org_id", "clickup_lists", ["organization_id"])
    op.create_index("ix_clickup_lists_ext", "clickup_lists", ["external_id"])

    op.create_table(
        "clickup_tasks_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("status", sa.String(100), nullable=True),
        sa.Column("assignees", sa.Text, nullable=False, server_default="[]"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("tags", sa.Text, nullable=False, server_default="[]"),
        sa.Column("list_id", sa.String(100), nullable=True),
        sa.Column("folder_id", sa.String(100), nullable=True),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("updated_at_remote", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clickup_tasks_snapshot_org_id", "clickup_tasks_snapshot", ["organization_id"])
    op.create_index("ix_clickup_tasks_snapshot_ext", "clickup_tasks_snapshot", ["external_id"])
    op.create_index("ix_clickup_tasks_snapshot_synced", "clickup_tasks_snapshot", ["synced_at"])

    op.create_table(
        "do_droplet_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("droplet_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("size", sa.String(100), nullable=True),
        sa.Column("status", sa.String(100), nullable=True),
        sa.Column("backups_enabled", sa.Boolean, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_do_droplet_snapshot_org_id", "do_droplet_snapshot", ["organization_id"])
    op.create_index("ix_do_droplet_snapshot_droplet", "do_droplet_snapshot", ["droplet_id"])
    op.create_index("ix_do_droplet_snapshot_synced", "do_droplet_snapshot", ["synced_at"])

    op.create_table(
        "do_team_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_do_team_snapshot_org_id", "do_team_snapshot", ["organization_id"])
    op.create_index("ix_do_team_snapshot_email", "do_team_snapshot", ["email"])
    op.create_index("ix_do_team_snapshot_synced", "do_team_snapshot", ["synced_at"])

    op.create_table(
        "do_cost_snapshot",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("amount_usd", sa.Float, nullable=True),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_do_cost_snapshot_org_id", "do_cost_snapshot", ["organization_id"])
    op.create_index("ix_do_cost_snapshot_synced", "do_cost_snapshot", ["synced_at"])

    op.create_table(
        "policy_violations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("details_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_policy_violations_org_id", "policy_violations", ["organization_id"])
    op.create_index("ix_policy_violations_platform", "policy_violations", ["platform"])
    op.create_index("ix_policy_violations_severity", "policy_violations", ["severity"])
    op.create_index("ix_policy_violations_created", "policy_violations", ["created_at"])

    op.create_table(
        "ceo_summaries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("summary_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ceo_summaries_org_id", "ceo_summaries", ["organization_id"])
    op.create_index("ix_ceo_summaries_created", "ceo_summaries", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ceo_summaries_created", table_name="ceo_summaries")
    op.drop_index("ix_ceo_summaries_org_id", table_name="ceo_summaries")
    op.drop_table("ceo_summaries")

    op.drop_index("ix_policy_violations_created", table_name="policy_violations")
    op.drop_index("ix_policy_violations_severity", table_name="policy_violations")
    op.drop_index("ix_policy_violations_platform", table_name="policy_violations")
    op.drop_index("ix_policy_violations_org_id", table_name="policy_violations")
    op.drop_table("policy_violations")

    op.drop_index("ix_do_cost_snapshot_synced", table_name="do_cost_snapshot")
    op.drop_index("ix_do_cost_snapshot_org_id", table_name="do_cost_snapshot")
    op.drop_table("do_cost_snapshot")

    op.drop_index("ix_do_team_snapshot_synced", table_name="do_team_snapshot")
    op.drop_index("ix_do_team_snapshot_email", table_name="do_team_snapshot")
    op.drop_index("ix_do_team_snapshot_org_id", table_name="do_team_snapshot")
    op.drop_table("do_team_snapshot")

    op.drop_index("ix_do_droplet_snapshot_synced", table_name="do_droplet_snapshot")
    op.drop_index("ix_do_droplet_snapshot_droplet", table_name="do_droplet_snapshot")
    op.drop_index("ix_do_droplet_snapshot_org_id", table_name="do_droplet_snapshot")
    op.drop_table("do_droplet_snapshot")

    op.drop_index("ix_clickup_tasks_snapshot_synced", table_name="clickup_tasks_snapshot")
    op.drop_index("ix_clickup_tasks_snapshot_ext", table_name="clickup_tasks_snapshot")
    op.drop_index("ix_clickup_tasks_snapshot_org_id", table_name="clickup_tasks_snapshot")
    op.drop_table("clickup_tasks_snapshot")

    op.drop_index("ix_clickup_lists_ext", table_name="clickup_lists")
    op.drop_index("ix_clickup_lists_org_id", table_name="clickup_lists")
    op.drop_table("clickup_lists")

    op.drop_index("ix_clickup_folders_ext", table_name="clickup_folders")
    op.drop_index("ix_clickup_folders_org_id", table_name="clickup_folders")
    op.drop_table("clickup_folders")

    op.drop_index("ix_clickup_spaces_ext", table_name="clickup_spaces")
    op.drop_index("ix_clickup_spaces_org_id", table_name="clickup_spaces")
    op.drop_table("clickup_spaces")

    op.drop_index("ix_gh_pr_snapshot_synced", table_name="github_pr_snapshot")
    op.drop_index("ix_gh_pr_snapshot_author", table_name="github_pr_snapshot")
    op.drop_index("ix_gh_pr_snapshot_repo", table_name="github_pr_snapshot")
    op.drop_index("ix_gh_pr_snapshot_org_id", table_name="github_pr_snapshot")
    op.drop_table("github_pr_snapshot")

    op.drop_index("ix_gh_repo_snapshot_synced", table_name="github_repo_snapshot")
    op.drop_index("ix_gh_repo_snapshot_repo", table_name="github_repo_snapshot")
    op.drop_index("ix_gh_repo_snapshot_org_id", table_name="github_repo_snapshot")
    op.drop_table("github_repo_snapshot")

    op.drop_index("ix_gh_role_snapshot_synced", table_name="github_role_snapshot")
    op.drop_index("ix_gh_role_snapshot_repo", table_name="github_role_snapshot")
    op.drop_index("ix_gh_role_snapshot_login", table_name="github_role_snapshot")
    op.drop_index("ix_gh_role_snapshot_org_id", table_name="github_role_snapshot")
    op.drop_table("github_role_snapshot")

    op.drop_constraint("uq_github_identity_map_org_email", "github_identity_map", type_="unique")
    op.drop_index("ix_github_identity_map_login", table_name="github_identity_map")
    op.drop_index("ix_github_identity_map_email", table_name="github_identity_map")
    op.drop_index("ix_github_identity_map_org_id", table_name="github_identity_map")
    op.drop_table("github_identity_map")

    op.drop_constraint("uq_org_people_org_email", "org_people", type_="unique")
    op.drop_index("ix_org_people_email", table_name="org_people")
    op.drop_index("ix_org_people_org_id", table_name="org_people")
    op.drop_table("org_people")
