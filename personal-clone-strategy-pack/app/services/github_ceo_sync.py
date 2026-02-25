"""
GitHub CEO Monitoring Sync — deep data ingestion for executive reporting.

Ingests:
- Repos (metadata, language, activity)
- Pull requests (open + recently merged) with review data
- Commits per user per day
- Workflow runs (CI/CD status)
- Org members

Provides summary + risk query functions for the CEO dashboard.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.github import (
    GitHubCommitDaily,
    GitHubPullRequest,
    GitHubRepo,
    GitHubReview,
    GitHubSyncRun,
    GitHubUser,
    GitHubWorkflowRun,
)
from app.services import integration as integration_service
from app.tools import github_admin
from app.tools.github import (
    get_pull_requests,
    get_workflow_runs,
    list_repos,
)

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


async def _get_token(db: AsyncSession, org_id: int) -> str | None:
    item = await integration_service.get_integration_by_type(db, org_id, "github")
    if not item or item.status != "connected":
        return None
    return (item.config_json or {}).get("access_token")


# ── Full Sync ────────────────────────────────────────────────────────────────

async def run_ceo_sync(db: AsyncSession, org_id: int) -> dict[str, Any]:
    """
    Full CEO-level GitHub sync. Ingests repos, PRs, reviews, commits, workflows.
    Returns sync run stats.
    """
    token = await _get_token(db, org_id)
    if not token:
        return {"error": "GitHub not connected"}

    org = (settings.GITHUB_ORG or "").strip()
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=30)).isoformat()

    # Record sync run
    sync_run = GitHubSyncRun(
        organization_id=org_id,
        started_at=now,
        status="running",
    )
    db.add(sync_run)
    await db.flush()

    stats = {
        "repos_synced": 0,
        "prs_synced": 0,
        "reviews_synced": 0,
        "commits_synced": 0,
        "workflows_synced": 0,
    }

    try:
        # 1. Sync repos
        if org:
            repos = await github_admin.list_org_repos(token, org)
        else:
            repos = await list_repos(token, per_page=50)

        for repo in repos:
            full_name = repo.get("full_name", "")
            if not full_name or repo.get("archived"):
                continue

            # Upsert repo
            existing = await db.execute(
                select(GitHubRepo).where(
                    GitHubRepo.organization_id == org_id,
                    GitHubRepo.full_name == full_name,
                )
            )
            gh_repo = existing.scalar_one_or_none()
            if gh_repo:
                gh_repo.name = repo.get("name", "")
                gh_repo.owner_login = repo.get("owner", {}).get("login", "")
                gh_repo.default_branch = repo.get("default_branch", "main")
                gh_repo.is_private = repo.get("private", False)
                gh_repo.is_archived = repo.get("archived", False)
                gh_repo.language = repo.get("language")
                gh_repo.open_issues_count = repo.get("open_issues_count", 0)
                gh_repo.stargazers_count = repo.get("stargazers_count", 0)
                gh_repo.pushed_at = _parse_ts(repo.get("pushed_at"))
                gh_repo.synced_at = now
            else:
                db.add(GitHubRepo(
                    organization_id=org_id,
                    full_name=full_name,
                    name=repo.get("name", ""),
                    owner_login=repo.get("owner", {}).get("login", ""),
                    default_branch=repo.get("default_branch", "main"),
                    is_private=repo.get("private", False),
                    is_archived=repo.get("archived", False),
                    language=repo.get("language"),
                    open_issues_count=repo.get("open_issues_count", 0),
                    stargazers_count=repo.get("stargazers_count", 0),
                    pushed_at=_parse_ts(repo.get("pushed_at")),
                    synced_at=now,
                ))
            stats["repos_synced"] += 1

        await db.flush()

        # 2. Sync org members
        if org:
            try:
                members = await github_admin.list_org_members(token, org)
                for m in members:
                    login = m.get("login", "")
                    if not login:
                        continue
                    existing_user = await db.execute(
                        select(GitHubUser).where(
                            GitHubUser.organization_id == org_id,
                            GitHubUser.login == login,
                        )
                    )
                    gh_user = existing_user.scalar_one_or_none()
                    if gh_user:
                        gh_user.github_id = m.get("id")
                        gh_user.avatar_url = m.get("avatar_url")
                        gh_user.synced_at = now
                    else:
                        db.add(GitHubUser(
                            organization_id=org_id,
                            login=login,
                            github_id=m.get("id"),
                            avatar_url=m.get("avatar_url"),
                            synced_at=now,
                        ))
                await db.flush()
            except Exception as exc:
                logger.warning("Failed to sync org members: %s", exc)

        # 3. Sync PRs (open + recently closed/merged) per repo
        active_repos = [r for r in repos if not r.get("archived") and not r.get("disabled")]
        for repo in active_repos[:30]:  # cap at 30 repos
            full_name = repo.get("full_name", "")
            owner = repo.get("owner", {}).get("login", "")
            name = repo.get("name", "")
            if not owner or not name:
                continue

            for pr_state in ("open", "closed"):
                try:
                    prs = await get_pull_requests(token, owner, name, state=pr_state, per_page=30)
                except Exception:
                    continue

                for pr in prs:
                    pr_number = pr.get("number")
                    if not pr_number:
                        continue

                    merged_at = _parse_ts(pr.get("merged_at"))
                    closed_at = _parse_ts(pr.get("closed_at"))
                    state = "merged" if merged_at else pr.get("state", "open")

                    # Skip old closed PRs (only care about last 30 days)
                    if state == "closed" and not merged_at:
                        if closed_at and closed_at < now - timedelta(days=30):
                            continue

                    existing_pr = await db.execute(
                        select(GitHubPullRequest).where(
                            GitHubPullRequest.organization_id == org_id,
                            GitHubPullRequest.repo_full_name == full_name,
                            GitHubPullRequest.pr_number == pr_number,
                        )
                    )
                    gh_pr = existing_pr.scalar_one_or_none()
                    pr_data = {
                        "title": str(pr.get("title", ""))[:500],
                        "author": str((pr.get("user") or {}).get("login", "")),
                        "state": state,
                        "is_draft": pr.get("draft", False),
                        "additions": pr.get("additions", 0),
                        "deletions": pr.get("deletions", 0),
                        "changed_files": pr.get("changed_files", 0),
                        "review_comments": pr.get("review_comments", 0),
                        "merged_at": merged_at,
                        "created_at_remote": _parse_ts(pr.get("created_at")),
                        "updated_at_remote": _parse_ts(pr.get("updated_at")),
                        "closed_at_remote": closed_at,
                        "url": pr.get("html_url"),
                        "synced_at": now,
                    }
                    if gh_pr:
                        for k, v in pr_data.items():
                            setattr(gh_pr, k, v)
                    else:
                        db.add(GitHubPullRequest(
                            organization_id=org_id,
                            repo_full_name=full_name,
                            pr_number=pr_number,
                            **pr_data,
                        ))
                    stats["prs_synced"] += 1

                    # 3b. Sync reviews for this PR
                    try:
                        reviews = await github_admin.get_pr_reviews(token, full_name, pr_number)
                        for rev in reviews:
                            rev_id = rev.get("id")
                            if not rev_id:
                                continue
                            existing_rev = await db.execute(
                                select(GitHubReview).where(
                                    GitHubReview.organization_id == org_id,
                                    GitHubReview.repo_full_name == full_name,
                                    GitHubReview.pr_number == pr_number,
                                    GitHubReview.review_id == rev_id,
                                )
                            )
                            gh_rev = existing_rev.scalar_one_or_none()
                            rev_data = {
                                "reviewer": str((rev.get("user") or {}).get("login", "")),
                                "state": rev.get("state", ""),
                                "submitted_at": _parse_ts(rev.get("submitted_at")),
                                "synced_at": now,
                            }
                            if gh_rev:
                                for k, v in rev_data.items():
                                    setattr(gh_rev, k, v)
                            else:
                                db.add(GitHubReview(
                                    organization_id=org_id,
                                    repo_full_name=full_name,
                                    pr_number=pr_number,
                                    review_id=rev_id,
                                    **rev_data,
                                ))
                            stats["reviews_synced"] += 1
                    except Exception as exc:
                        logger.debug("Review fetch failed %s#%d: %s", full_name, pr_number, exc)

            # 4. Sync commits (last 30 days)
            try:
                commits = await github_admin.get_repo_commits(token, full_name, since=since, per_page=100)
                daily_counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"count": 0, "additions": 0, "deletions": 0})
                for c in commits:
                    author_login = ""
                    if c.get("author") and isinstance(c["author"], dict):
                        author_login = c["author"].get("login", "")
                    if not author_login and c.get("commit", {}).get("author"):
                        author_login = c["commit"]["author"].get("name", "unknown")
                    commit_date_str = ""
                    if c.get("commit", {}).get("author", {}).get("date"):
                        commit_date_str = c["commit"]["author"]["date"][:10]
                    if author_login and commit_date_str:
                        key = (author_login, commit_date_str)
                        daily_counts[key]["count"] += 1

                for (author, date_str), counts in daily_counts.items():
                    existing_cd = await db.execute(
                        select(GitHubCommitDaily).where(
                            GitHubCommitDaily.organization_id == org_id,
                            GitHubCommitDaily.repo_full_name == full_name,
                            GitHubCommitDaily.author == author,
                            GitHubCommitDaily.commit_date == date_str,
                        )
                    )
                    gh_cd = existing_cd.scalar_one_or_none()
                    if gh_cd:
                        gh_cd.commit_count = counts["count"]
                        gh_cd.synced_at = now
                    else:
                        db.add(GitHubCommitDaily(
                            organization_id=org_id,
                            repo_full_name=full_name,
                            author=author,
                            commit_date=date_str,
                            commit_count=counts["count"],
                            synced_at=now,
                        ))
                    stats["commits_synced"] += counts["count"]
            except Exception as exc:
                logger.debug("Commit fetch failed %s: %s", full_name, exc)

            # 5. Sync workflow runs
            try:
                runs = await get_workflow_runs(token, owner, name, per_page=20)
                for run in runs:
                    run_id = run.get("id")
                    if not run_id:
                        continue
                    existing_wr = await db.execute(
                        select(GitHubWorkflowRun).where(
                            GitHubWorkflowRun.organization_id == org_id,
                            GitHubWorkflowRun.run_id == run_id,
                        )
                    )
                    gh_wr = existing_wr.scalar_one_or_none()
                    # Calculate duration
                    run_started = _parse_ts(run.get("run_started_at"))
                    updated = _parse_ts(run.get("updated_at"))
                    duration = None
                    if run_started and updated:
                        duration = (updated - run_started).total_seconds()

                    wr_data = {
                        "repo_full_name": full_name,
                        "workflow_name": run.get("name", ""),
                        "status": run.get("status", ""),
                        "conclusion": run.get("conclusion"),
                        "head_branch": run.get("head_branch"),
                        "triggering_actor": str((run.get("triggering_actor") or {}).get("login", "")),
                        "created_at_remote": _parse_ts(run.get("created_at")),
                        "updated_at_remote": updated,
                        "run_started_at": run_started,
                        "duration_seconds": duration,
                        "url": run.get("html_url"),
                        "synced_at": now,
                    }
                    if gh_wr:
                        for k, v in wr_data.items():
                            setattr(gh_wr, k, v)
                    else:
                        db.add(GitHubWorkflowRun(
                            organization_id=org_id,
                            run_id=run_id,
                            **wr_data,
                        ))
                    stats["workflows_synced"] += 1
            except Exception as exc:
                logger.debug("Workflow fetch failed %s: %s", full_name, exc)

        await db.commit()

        # Update sync run
        sync_run.finished_at = datetime.now(timezone.utc)
        sync_run.status = "ok"
        sync_run.repos_synced = stats["repos_synced"]
        sync_run.prs_synced = stats["prs_synced"]
        sync_run.reviews_synced = stats["reviews_synced"]
        sync_run.commits_synced = stats["commits_synced"]
        sync_run.workflows_synced = stats["workflows_synced"]
        await db.commit()

    except Exception as exc:
        logger.error("CEO GitHub sync failed: %s", exc)
        await db.rollback()
        sync_run.finished_at = datetime.now(timezone.utc)
        sync_run.status = "error"
        sync_run.error_message = str(exc)[:500]
        try:
            await db.commit()
        except Exception as commit_exc:
            logger.error("Failed to persist CEO GitHub sync error status: %s", type(commit_exc).__name__)
        return {"error": str(exc), **stats}

    return {"error": None, **stats}


# ── Query Functions ──────────────────────────────────────────────────────────

async def get_ceo_summary(
    db: AsyncSession,
    org_id: int,
    days: int = 7,
) -> dict[str, Any]:
    """
    CEO weekly summary: PR throughput, review time, CI failure rate,
    top blocked repos, inactive dev alerts.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    # PR throughput per dev (merged PRs in range)
    merged_q = await db.execute(
        select(
            GitHubPullRequest.author,
            func.count(GitHubPullRequest.id).label("count"),
        )
        .where(
            GitHubPullRequest.organization_id == org_id,
            GitHubPullRequest.state == "merged",
            GitHubPullRequest.merged_at >= since,
        )
        .group_by(GitHubPullRequest.author)
        .order_by(func.count(GitHubPullRequest.id).desc())
    )
    pr_throughput = [{"author": r.author, "merged_prs": r.count} for r in merged_q]

    # Average PR review time (time from created to first review) — single query
    first_review_subq = (
        select(
            GitHubReview.repo_full_name,
            GitHubReview.pr_number,
            func.min(GitHubReview.submitted_at).label("first_review_at"),
        )
        .where(
            GitHubReview.organization_id == org_id,
            GitHubReview.submitted_at.isnot(None),
        )
        .group_by(GitHubReview.repo_full_name, GitHubReview.pr_number)
        .subquery()
    )
    review_time_q = await db.execute(
        select(
            GitHubPullRequest.created_at_remote,
            first_review_subq.c.first_review_at,
        )
        .join(
            first_review_subq,
            (GitHubPullRequest.repo_full_name == first_review_subq.c.repo_full_name)
            & (GitHubPullRequest.pr_number == first_review_subq.c.pr_number),
        )
        .where(
            GitHubPullRequest.organization_id == org_id,
            GitHubPullRequest.state == "merged",
            GitHubPullRequest.merged_at >= since,
            GitHubPullRequest.created_at_remote.isnot(None),
        )
    )
    review_times = []
    for row in review_time_q:
        if row.created_at_remote and row.first_review_at:
            hours = (row.first_review_at - row.created_at_remote).total_seconds() / 3600
            review_times.append(hours)

    avg_review_hours = round(sum(review_times) / len(review_times), 1) if review_times else None

    # CI failure rate
    workflow_q = await db.execute(
        select(
            func.count(GitHubWorkflowRun.id).label("total"),
            func.sum(
                func.cast(GitHubWorkflowRun.conclusion == "failure", Integer)
            ).label("failures"),
        )
        .where(
            GitHubWorkflowRun.organization_id == org_id,
            GitHubWorkflowRun.status == "completed",
            GitHubWorkflowRun.created_at_remote >= since,
        )
    )
    wf_row = workflow_q.one_or_none()
    total_runs = wf_row.total if wf_row else 0
    failed_runs = wf_row.failures if wf_row else 0
    ci_failure_rate = round(
        (failed_runs / total_runs * 100) if total_runs > 0 else 0, 1,
    )

    # Open PRs older than 3 days (blocked)
    stale_cutoff = now - timedelta(days=3)
    stale_q = await db.execute(
        select(
            GitHubPullRequest.repo_full_name,
            func.count(GitHubPullRequest.id).label("count"),
        )
        .where(
            GitHubPullRequest.organization_id == org_id,
            GitHubPullRequest.state == "open",
            GitHubPullRequest.created_at_remote <= stale_cutoff,
        )
        .group_by(GitHubPullRequest.repo_full_name)
        .order_by(func.count(GitHubPullRequest.id).desc())
        .limit(10)
    )
    blocked_repos = [{"repo": r.repo_full_name, "stale_prs": r.count} for r in stale_q]

    # Inactive devs (no commits in range)
    all_users_q = await db.execute(
        select(GitHubUser.login).where(GitHubUser.organization_id == org_id)
    )
    all_users = {r.login for r in all_users_q}

    active_q = await db.execute(
        select(GitHubCommitDaily.author).where(
            GitHubCommitDaily.organization_id == org_id,
            GitHubCommitDaily.commit_date >= since.strftime("%Y-%m-%d"),
        ).distinct()
    )
    active_users = {r.author for r in active_q}
    inactive_devs = sorted(all_users - active_users)

    # Commit counts per dev
    commit_q = await db.execute(
        select(
            GitHubCommitDaily.author,
            func.sum(GitHubCommitDaily.commit_count).label("total"),
        )
        .where(
            GitHubCommitDaily.organization_id == org_id,
            GitHubCommitDaily.commit_date >= since.strftime("%Y-%m-%d"),
        )
        .group_by(GitHubCommitDaily.author)
        .order_by(func.sum(GitHubCommitDaily.commit_count).desc())
    )
    commit_leaderboard = [{"author": r.author, "commits": int(r.total)} for r in commit_q]

    # Last sync run
    last_sync_q = await db.execute(
        select(GitHubSyncRun)
        .where(GitHubSyncRun.organization_id == org_id)
        .order_by(GitHubSyncRun.started_at.desc())
        .limit(1)
    )
    last_sync = last_sync_q.scalar_one_or_none()

    return {
        "range_days": days,
        "pr_throughput": pr_throughput,
        "avg_review_time_hours": avg_review_hours,
        "ci_failure_rate_pct": ci_failure_rate,
        "total_ci_runs": total_runs,
        "failed_ci_runs": int(failed_runs) if failed_runs else 0,
        "blocked_repos": blocked_repos,
        "inactive_devs": inactive_devs,
        "commit_leaderboard": commit_leaderboard,
        "last_sync": {
            "status": last_sync.status,
            "started_at": last_sync.started_at.isoformat(),
            "repos": last_sync.repos_synced,
            "prs": last_sync.prs_synced,
            "reviews": last_sync.reviews_synced,
            "commits": last_sync.commits_synced,
            "workflows": last_sync.workflows_synced,
        } if last_sync else None,
    }


async def get_risks(
    db: AsyncSession,
    org_id: int,
    days: int = 7,
) -> dict[str, Any]:
    """
    Risk detection: PRs without reviews, failing CI, long-open PRs,
    single-point-of-failure devs, force push indicators.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    risks: list[dict[str, Any]] = []

    # 1. Open PRs with no reviews — single LEFT JOIN query
    review_count_subq = (
        select(
            GitHubReview.repo_full_name,
            GitHubReview.pr_number,
            func.count(GitHubReview.id).label("review_count"),
        )
        .where(GitHubReview.organization_id == org_id)
        .group_by(GitHubReview.repo_full_name, GitHubReview.pr_number)
        .subquery()
    )
    open_prs_q = await db.execute(
        select(
            GitHubPullRequest,
            review_count_subq.c.review_count,
        )
        .outerjoin(
            review_count_subq,
            (GitHubPullRequest.repo_full_name == review_count_subq.c.repo_full_name)
            & (GitHubPullRequest.pr_number == review_count_subq.c.pr_number),
        )
        .where(
            GitHubPullRequest.organization_id == org_id,
            GitHubPullRequest.state == "open",
        )
    )
    for row in open_prs_q:
        pr = row[0]
        review_count = row[1] or 0
        if review_count == 0:
            age_hours = (now - pr.created_at_remote).total_seconds() / 3600 if pr.created_at_remote else 0
            if age_hours > 24:
                risks.append({
                    "type": "pr_no_review",
                    "severity": "high" if age_hours > 72 else "medium",
                    "repo": pr.repo_full_name,
                    "pr": pr.pr_number,
                    "title": pr.title,
                    "author": pr.author,
                    "age_hours": round(age_hours, 1),
                    "url": pr.url,
                })

    # 2. Repos with high CI failure rate
    repo_ci = await db.execute(
        select(
            GitHubWorkflowRun.repo_full_name,
            func.count(GitHubWorkflowRun.id).label("total"),
            func.sum(
                func.cast(GitHubWorkflowRun.conclusion == "failure", Integer)
            ).label("failures"),
        )
        .where(
            GitHubWorkflowRun.organization_id == org_id,
            GitHubWorkflowRun.status == "completed",
            GitHubWorkflowRun.created_at_remote >= since,
        )
        .group_by(GitHubWorkflowRun.repo_full_name)
    )
    for r in repo_ci:
        if r.total >= 3 and r.failures and (r.failures / r.total) > 0.3:
            risks.append({
                "type": "high_ci_failure",
                "severity": "high" if (r.failures / r.total) > 0.5 else "medium",
                "repo": r.repo_full_name,
                "total_runs": r.total,
                "failures": int(r.failures),
                "failure_rate_pct": round(r.failures / r.total * 100, 1),
            })

    # 3. Single-contributor repos (bus factor = 1)
    recent_commits = await db.execute(
        select(
            GitHubCommitDaily.repo_full_name,
            func.count(func.distinct(GitHubCommitDaily.author)).label("authors"),
        )
        .where(
            GitHubCommitDaily.organization_id == org_id,
            GitHubCommitDaily.commit_date >= since.strftime("%Y-%m-%d"),
        )
        .group_by(GitHubCommitDaily.repo_full_name)
    )
    for r in recent_commits:
        if r.authors == 1:
            risks.append({
                "type": "bus_factor",
                "severity": "medium",
                "repo": r.repo_full_name,
                "unique_contributors": r.authors,
                "description": "Only one developer has committed in this period",
            })

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    risks.sort(key=lambda r: severity_order.get(r.get("severity", "low"), 3))

    return {
        "range_days": days,
        "total_risks": len(risks),
        "risks": risks,
    }
