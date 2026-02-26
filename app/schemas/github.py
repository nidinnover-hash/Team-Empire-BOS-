"""Schemas for GitHub governance + CEO monitoring endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Governance ───────────────────────────────────────────────────────────────

class GovernanceApplyResponse(BaseModel):
    teams: list[dict[str, Any]] = Field(default_factory=list)
    permissions: list[dict[str, Any]] = Field(default_factory=list)
    branch_protections: list[dict[str, Any]] = Field(default_factory=list)
    codeowners: list[dict[str, Any]] = Field(default_factory=list)
    templates: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


# ── CEO Sync ─────────────────────────────────────────────────────────────────

class GitHubCEOSyncResult(BaseModel):
    repos_synced: int = 0
    prs_synced: int = 0
    reviews_synced: int = 0
    commits_synced: int = 0
    workflows_synced: int = 0
    error: str | None = None


class GitHubCEOSummary(BaseModel):
    range_days: int
    pr_throughput: list[dict[str, Any]]
    avg_review_time_hours: float | None
    ci_failure_rate_pct: float
    total_ci_runs: int
    failed_ci_runs: int
    blocked_repos: list[dict[str, Any]]
    inactive_devs: list[str]
    commit_leaderboard: list[dict[str, Any]]
    last_sync: dict[str, Any] | None


class GitHubRiskReport(BaseModel):
    range_days: int
    total_risks: int
    risks: list[dict[str, Any]]
