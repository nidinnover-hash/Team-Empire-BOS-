"""GitHub governance + CEO monitoring tables.

Revision ID: 0021
Revises: 0020
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_repos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("full_name", sa.String(255), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_login", sa.String(255), nullable=False),
        sa.Column("default_branch", sa.String(120), nullable=False, server_default="main"),
        sa.Column("is_private", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("language", sa.String(100), nullable=True),
        sa.Column("open_issues_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stargazers_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.UniqueConstraint("organization_id", "full_name", name="uq_gh_repo_org_name"),
    )

    op.create_table(
        "github_users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("login", sa.String(255), nullable=False, index=True),
        sa.Column("github_id", sa.Integer, nullable=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.UniqueConstraint("organization_id", "login", name="uq_gh_user_org_login"),
    )

    op.create_table(
        "github_pull_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("repo_full_name", sa.String(255), nullable=False, index=True),
        sa.Column("pr_number", sa.Integer, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(255), nullable=False, index=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("is_draft", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("additions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("changed_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("review_comments", sa.Integer, nullable=False, server_default="0"),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_remote", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_remote", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at_remote", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.UniqueConstraint("organization_id", "repo_full_name", "pr_number", name="uq_gh_pr_org_repo_num"),
    )

    op.create_table(
        "github_reviews",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("repo_full_name", sa.String(255), nullable=False, index=True),
        sa.Column("pr_number", sa.Integer, nullable=False),
        sa.Column("review_id", sa.Integer, nullable=False),
        sa.Column("reviewer", sa.String(255), nullable=False, index=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.UniqueConstraint("organization_id", "repo_full_name", "pr_number", "review_id", name="uq_gh_review"),
    )

    op.create_table(
        "github_commits_daily",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("repo_full_name", sa.String(255), nullable=False, index=True),
        sa.Column("author", sa.String(255), nullable=False, index=True),
        sa.Column("commit_date", sa.String(10), nullable=False),
        sa.Column("commit_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("additions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.UniqueConstraint("organization_id", "repo_full_name", "author", "commit_date", name="uq_gh_commit_daily"),
    )

    op.create_table(
        "github_workflow_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("repo_full_name", sa.String(255), nullable=False, index=True),
        sa.Column("run_id", sa.Integer, nullable=False, index=True),
        sa.Column("workflow_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("conclusion", sa.String(30), nullable=True),
        sa.Column("head_branch", sa.String(255), nullable=True),
        sa.Column("triggering_actor", sa.String(255), nullable=True),
        sa.Column("created_at_remote", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at_remote", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.UniqueConstraint("organization_id", "run_id", name="uq_gh_workflow_run"),
    )

    op.create_table(
        "github_sync_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("repos_synced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prs_synced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reviews_synced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("commits_synced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("workflows_synced", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("github_sync_runs")
    op.drop_table("github_workflow_runs")
    op.drop_table("github_commits_daily")
    op.drop_table("github_reviews")
    op.drop_table("github_pull_requests")
    op.drop_table("github_users")
    op.drop_table("github_repos")
