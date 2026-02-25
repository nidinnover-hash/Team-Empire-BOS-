"""GitHub governance + CEO monitoring data models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GitHubRepo(Base):
    __tablename__ = "github_repos"
    __table_args__ = (
        UniqueConstraint("organization_id", "full_name", name="uq_gh_repo_org_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_login: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(120), nullable=False, default="main")
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str | None] = mapped_column(String(100), nullable=True)
    open_issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stargazers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GitHubUser(Base):
    __tablename__ = "github_users"
    __table_args__ = (
        UniqueConstraint("organization_id", "login", name="uq_gh_user_org_login"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    login: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    github_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)  # owner, member
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GitHubPullRequest(Base):
    __tablename__ = "github_pull_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "repo_full_name", "pr_number", name="uq_gh_pr_org_repo_num"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)  # open, closed, merged
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    additions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_remote: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_remote: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at_remote: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GitHubReview(Base):
    __tablename__ = "github_reviews"
    __table_args__ = (
        UniqueConstraint("organization_id", "repo_full_name", "pr_number", "review_id", name="uq_gh_review"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False)  # APPROVED, CHANGES_REQUESTED, COMMENTED
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GitHubCommitDaily(Base):
    __tablename__ = "github_commits_daily"
    __table_args__ = (
        UniqueConstraint("organization_id", "repo_full_name", "author", "commit_date", name="uq_gh_commit_daily"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    commit_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    commit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    additions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GitHubWorkflowRun(Base):
    __tablename__ = "github_workflow_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "run_id", name="uq_gh_workflow_run"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # queued, in_progress, completed
    conclusion: Mapped[str | None] = mapped_column(String(30), nullable=True)  # success, failure, cancelled
    head_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    triggering_actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at_remote: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_remote: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GitHubSyncRun(Base):
    __tablename__ = "github_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")  # running, ok, error
    repos_synced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prs_synced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviews_synced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    commits_synced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    workflows_synced: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
