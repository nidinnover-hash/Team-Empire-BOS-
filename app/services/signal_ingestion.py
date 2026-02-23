"""
Ops Intelligence signal ingestion.

Pulls data from ClickUp, GitHub, and Gmail integrations,
sanitizes it, and stores as IntegrationSignal rows.
All operations are read-only (observer mode) — no writes to external services.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.employee import Employee
from app.models.integration import Integration
from app.models.integration_signal import IntegrationSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SANITIZE_KEYS = {"access_token", "refresh_token", "token", "secret", "password", "api_key"}


def _sanitize_payload(raw: dict) -> dict:
    """Remove secrets/tokens from payload before storage."""
    clean = {}
    for k, v in raw.items():
        if k.lower() in _SANITIZE_KEYS:
            continue
        if isinstance(v, dict):
            clean[k] = _sanitize_payload(v)
        else:
            clean[k] = v
    return clean


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _work_email_domains() -> set[str]:
    raw = settings.WORK_EMAIL_DOMAINS.strip()
    if not raw:
        return set()
    return {d.strip().lower() for d in raw.split(",") if d.strip()}


def _gmail_label_allowlist() -> set[str]:
    raw = settings.GMAIL_LABEL_ALLOWLIST.strip()
    if not raw:
        return set()
    return {label.strip() for label in raw.split(",") if label.strip()}


async def _get_integration(db: AsyncSession, org_id: int, itype: str) -> Integration | None:
    result = await db.execute(
        select(Integration).where(
            Integration.organization_id == org_id,
            Integration.type == itype,
            Integration.status == "connected",
        )
    )
    return cast(Integration | None, result.scalar_one_or_none())


async def _employee_map(
    db: AsyncSession,
    org_id: int,
) -> dict[str, dict[str, int]]:
    """Build lookup maps: email->id, github_username->id, clickup_user_id->id."""
    result = await db.execute(
        select(Employee).where(Employee.organization_id == org_id, Employee.is_active == True)  # noqa: E712
    )
    employees = result.scalars().all()
    maps: dict[str, dict[str, int]] = {"email": {}, "github": {}, "clickup": {}}
    for emp in employees:
        if emp.email:
            maps["email"][emp.email.lower()] = emp.id
        if emp.github_username:
            maps["github"][emp.github_username.lower()] = emp.id
        if emp.clickup_user_id:
            maps["clickup"][emp.clickup_user_id] = emp.id
    return maps


async def _upsert_signal(
    db: AsyncSession,
    org_id: int,
    source: str,
    external_id: str,
    employee_id: int | None,
    timestamp: datetime,
    payload: dict,
) -> IntegrationSignal:
    sanitized = _sanitize_payload(payload)
    payload_hash = _hash_payload(sanitized)
    payload_str = json.dumps(sanitized, default=str)

    result = await db.execute(
        select(IntegrationSignal).where(
            IntegrationSignal.organization_id == org_id,
            IntegrationSignal.source == source,
            IntegrationSignal.external_id == external_id,
        )
    )
    existing = cast(IntegrationSignal | None, result.scalar_one_or_none())

    if existing:
        if existing.hash != payload_hash:
            existing.payload_json = payload_str
            existing.hash = payload_hash
            existing.employee_id = employee_id
            existing.timestamp = timestamp
        return existing

    signal = IntegrationSignal(
        organization_id=org_id,
        source=source,
        external_id=external_id,
        employee_id=employee_id,
        timestamp=timestamp,
        payload_json=payload_str,
        hash=payload_hash,
    )
    db.add(signal)
    return signal


# ---------------------------------------------------------------------------
# ClickUp ingestion
# ---------------------------------------------------------------------------

async def ingest_clickup_signals(db: AsyncSession, org_id: int) -> dict:
    """Fetch ClickUp tasks and store as IntegrationSignal rows."""
    from app.tools import clickup as clickup_tool

    integration = await _get_integration(db, org_id, "clickup")
    if not integration:
        return {"synced": 0, "error": "ClickUp not connected"}

    config = integration.config_json or {}
    api_token = config.get("access_token")
    team_id = config.get("team_id")
    if not api_token or not team_id:
        return {"synced": 0, "error": "Missing ClickUp credentials"}

    emp_maps = await _employee_map(db, org_id)

    try:
        tasks = await clickup_tool.get_tasks(api_token, team_id, include_closed=True)
    except Exception as exc:
        logger.warning("ClickUp signal ingestion failed for org %d: %s", org_id, exc)
        return {"synced": 0, "error": str(exc)}

    count = 0
    for task in tasks:
        task_id = str(task.get("id", ""))
        if not task_id:
            continue

        # Map assignee to employee
        assignees = task.get("assignees", [])
        employee_id = None
        for assignee in assignees:
            cu_id = str(assignee.get("id", ""))
            if cu_id in emp_maps["clickup"]:
                employee_id = emp_maps["clickup"][cu_id]
                break

        ts_str = task.get("date_updated") or task.get("date_created")
        try:
            ts = datetime.fromtimestamp(int(ts_str) / 1000, tz=timezone.utc) if ts_str else datetime.now(timezone.utc)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)

        payload = {
            "name": task.get("name"),
            "status": task.get("status", {}).get("status") if isinstance(task.get("status"), dict) else task.get("status"),
            "priority": clickup_tool.parse_priority(task),
            "due_date": clickup_tool.parse_due_date(task),
            "assignees": [a.get("username", "") for a in assignees],
            "tags": [t.get("name", "") for t in task.get("tags", [])],
            "list_name": task.get("list", {}).get("name") if isinstance(task.get("list"), dict) else None,
        }

        await _upsert_signal(db, org_id, "clickup", f"task:{task_id}", employee_id, ts, payload)
        count += 1

    await db.commit()
    return {"synced": count, "error": None}


# ---------------------------------------------------------------------------
# GitHub ingestion
# ---------------------------------------------------------------------------

async def ingest_github_signals(db: AsyncSession, org_id: int) -> dict:
    """Fetch GitHub PRs and issues, store as IntegrationSignal rows."""
    from app.tools import github as github_tool

    integration = await _get_integration(db, org_id, "github")
    if not integration:
        return {"synced": 0, "error": "GitHub not connected"}

    config = integration.config_json or {}
    token = config.get("access_token")
    if not token:
        return {"synced": 0, "error": "Missing GitHub token"}

    emp_maps = await _employee_map(db, org_id)

    try:
        repos = await github_tool.list_repos(token)
    except Exception as exc:
        logger.warning("GitHub signal ingestion failed for org %d: %s", org_id, exc)
        return {"synced": 0, "error": str(exc)}

    count = 0
    for repo in repos[:20]:  # Cap to avoid API rate limits
        owner = repo.get("owner", {}).get("login", "")
        repo_name = repo.get("name", "")
        if not owner or not repo_name:
            continue

        # PRs
        try:
            prs = await github_tool.get_pull_requests(token, owner, repo_name, state="all", per_page=30)
        except Exception:
            prs = []

        for pr in prs:
            pr_number = str(pr.get("number", ""))
            user_login = (pr.get("user", {}) or {}).get("login", "").lower()
            employee_id = emp_maps["github"].get(user_login)

            ts_str = pr.get("updated_at") or pr.get("created_at")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.now(timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)

            payload = {
                "title": pr.get("title"),
                "state": pr.get("state"),
                "repo": f"{owner}/{repo_name}",
                "author": user_login,
                "merged": pr.get("merged_at") is not None,
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "changed_files": pr.get("changed_files", 0),
                "review_comments": pr.get("review_comments", 0),
            }

            await _upsert_signal(db, org_id, "github", f"pr:{owner}/{repo_name}#{pr_number}", employee_id, ts, payload)
            count += 1

        # Issues (not PRs)
        try:
            issues = await github_tool.get_issues(token, owner, repo_name, state="all", per_page=30)
        except Exception:
            issues = []

        for issue in issues:
            issue_number = str(issue.get("number", ""))
            user_login = (issue.get("user", {}) or {}).get("login", "").lower()
            employee_id = emp_maps["github"].get(user_login)

            ts_str = issue.get("updated_at") or issue.get("created_at")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else datetime.now(timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)

            payload = {
                "title": issue.get("title"),
                "state": issue.get("state"),
                "repo": f"{owner}/{repo_name}",
                "author": user_login,
                "labels": [label.get("name", "") for label in issue.get("labels", [])],
            }

            await _upsert_signal(db, org_id, "github", f"issue:{owner}/{repo_name}#{issue_number}", employee_id, ts, payload)
            count += 1

    await db.commit()
    return {"synced": count, "error": None}


# ---------------------------------------------------------------------------
# Gmail ingestion (metadata only — no raw body storage)
# ---------------------------------------------------------------------------

async def ingest_gmail_signals(db: AsyncSession, org_id: int) -> dict:
    """
    Fetch Gmail threads (metadata only), store as IntegrationSignal rows.
    Respects WORK_EMAIL_DOMAINS allowlist — skips non-work emails.
    NEVER stores raw email body.
    """
    from app.tools import gmail as gmail_tool

    integration = await _get_integration(db, org_id, "gmail")
    if not integration:
        return {"synced": 0, "error": "Gmail not connected"}

    config = integration.config_json or {}
    access_token = config.get("access_token")
    refresh_token = config.get("refresh_token")
    expires_at = config.get("expires_at")
    if not access_token:
        return {"synced": 0, "error": "Missing Gmail token"}

    allowed_domains = _work_email_domains()
    emp_maps = await _employee_map(db, org_id)

    try:
        emails, _refreshed = gmail_tool.fetch_recent_emails(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            max_results=50,
        )
    except Exception as exc:
        logger.warning("Gmail signal ingestion failed for org %d: %s", org_id, exc)
        return {"synced": 0, "error": str(exc)}

    count = 0
    skipped = 0
    for email in emails:
        msg_id = str(email.get("gmail_id") or email.get("id") or "")
        if not msg_id:
            continue

        sender = str(email.get("from_address") or email.get("from") or "").strip().lower()
        # Extract domain from sender
        sender_domain = ""
        if "@" in sender:
            sender_domain = sender.split("@")[-1].rstrip(">").strip()

        # Enforce work email domain allowlist
        if allowed_domains and sender_domain not in allowed_domains:
            skipped += 1
            continue

        # Map sender to employee
        sender_email = sender
        if "<" in sender and ">" in sender:
            sender_email = sender.split("<")[1].rstrip(">").strip()
        employee_id = emp_maps["email"].get(sender_email)

        ts_raw: Any = email.get("received_at") or email.get("date")
        ts_str = str(ts_raw) if ts_raw else ""
        try:
            ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now(timezone.utc)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Store metadata only — NO body
        payload = {
            "subject": email.get("subject", ""),
            "from": sender_email,
            "to": email.get("to_address") or email.get("to") or "",
            "thread_id": email.get("thread_id") or email.get("threadId") or "",
            "label_ids": email.get("labelIds") or [],
            "snippet": (email.get("snippet") or "")[:200],  # Truncated snippet only
        }

        await _upsert_signal(db, org_id, "gmail", f"msg:{msg_id}", employee_id, ts, payload)
        count += 1

    await db.commit()
    logger.info("Gmail ingestion org=%d: synced=%d skipped=%d (domain filter)", org_id, count, skipped)
    return {"synced": count, "skipped_non_work": skipped, "error": None}
