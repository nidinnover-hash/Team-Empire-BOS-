from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ceo_control import (
    ClickUpTaskSnapshot,
    DigitalOceanDropletSnapshot,
    DigitalOceanTeamSnapshot,
    GitHubIdentityMap,
    GitHubRepoSnapshot,
    GitHubRoleSnapshot,
    OrgPerson,
    PolicyViolation,
)


def _owner_emails() -> set[str]:
    return {e.strip().lower() for e in settings.COMPLIANCE_OWNER_EMAILS.split(",") if e.strip()}


def _dev_emails() -> set[str]:
    return {e.strip().lower() for e in settings.COMPLIANCE_DEV_EMAILS.split(",") if e.strip()}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_company_directory(db: AsyncSession, org_id: int) -> None:
    people = [
        ("nidin@empireoe.com", "Nidin", "OWNER", None),
        ("admin@empireoe.com", "Admin", "OWNER", None),
        ("sharon@empireoe.com", "Sharon", "TECH_LEAD", "nidin@empireoe.com"),
        ("mano@empireoe.com", "Mano", "OPS_MANAGER", "nidin@empireoe.com"),
        ("dev1@empireoe.com", "Dev 1", "DEVELOPER", "sharon@empireoe.com"),
        ("dev2@empireoe.com", "Dev 2", "DEVELOPER", "sharon@empireoe.com"),
        ("dev3@empireoe.com", "Dev 3", "DEVELOPER", "sharon@empireoe.com"),
        ("dev4@empireoe.com", "Dev 4", "DEVELOPER", "sharon@empireoe.com"),
    ]
    for email, name, role, manager in people:
        existing = await db.execute(
            select(OrgPerson).where(OrgPerson.organization_id == org_id, OrgPerson.email == email)
        )
        row = existing.scalar_one_or_none()
        if row:
            row.name = name
            row.internal_role = role
            row.manager_email = manager
            row.active = True
            row.updated_at = _now()
        else:
            db.add(
                OrgPerson(
                    organization_id=org_id,
                    email=email,
                    name=name,
                    internal_role=role,
                    active=True,
                    manager_email=manager,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )
    await db.commit()


def _severity_weight(sev: str) -> int:
    return {"LOW": 2, "MED": 5, "HIGH": 10, "CRITICAL": 20}.get(sev, 0)


async def _latest_synced_at(db: AsyncSession, org_id: int, model: type[Any]) -> datetime | None:
    result = await db.execute(
        select(model.synced_at).where(model.organization_id == org_id).order_by(model.synced_at.desc()).limit(1)
    )
    value = result.scalar_one_or_none()
    return value if isinstance(value, datetime) else None


async def run_compliance(db: AsyncSession, org_id: int) -> dict[str, Any]:
    await ensure_company_directory(db, org_id)

    # Mark existing OPEN violations as stale; will be refreshed below
    from sqlalchemy import update
    await db.execute(
        update(PolicyViolation)
        .where(PolicyViolation.organization_id == org_id, PolicyViolation.status == "OPEN")
        .values(status="STALE")
    )

    identity_rows = (
        await db.execute(select(GitHubIdentityMap).where(GitHubIdentityMap.organization_id == org_id))
    ).scalars().all()
    login_to_email = {row.github_login.lower(): row.company_email.lower() for row in identity_rows}

    violations: list[PolicyViolation] = []
    now = _now()
    gh_role_time = await _latest_synced_at(db, org_id, GitHubRoleSnapshot)
    gh_repo_time = await _latest_synced_at(db, org_id, GitHubRepoSnapshot)
    clickup_time = await _latest_synced_at(db, org_id, ClickUpTaskSnapshot)
    do_team_time = await _latest_synced_at(db, org_id, DigitalOceanTeamSnapshot)
    do_droplet_time = await _latest_synced_at(db, org_id, DigitalOceanDropletSnapshot)

    if gh_role_time:
        roles = (
            await db.execute(
                select(GitHubRoleSnapshot).where(
                    GitHubRoleSnapshot.organization_id == org_id,
                    GitHubRoleSnapshot.synced_at == gh_role_time,
                )
            )
        ).scalars().all()
        for r in roles:
            email = login_to_email.get((r.github_login or "").lower())
            if (r.org_role or "").lower() == "owner" and email not in _owner_emails():
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="github",
                        severity="CRITICAL",
                        title="Unauthorized GitHub org owner",
                        details_json=json.dumps({"github_login": r.github_login, "mapped_email": email}),
                        status="OPEN",
                        created_at=now,
                    )
                )
            if email in _dev_emails() and (r.repo_permission or "").lower() in {"admin", "maintain"}:
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="github",
                        severity="CRITICAL",
                        title="Developer has elevated repo permission",
                        details_json=json.dumps(
                            {
                                "github_login": r.github_login,
                                "repo_name": r.repo_name,
                                "repo_permission": r.repo_permission,
                            }
                        ),
                        status="OPEN",
                        created_at=now,
                    )
                )

    if gh_repo_time:
        repos = (
            await db.execute(
                select(GitHubRepoSnapshot).where(
                    GitHubRepoSnapshot.organization_id == org_id,
                    GitHubRepoSnapshot.synced_at == gh_repo_time,
                )
            )
        ).scalars().all()
        for repo in repos:
            if not repo.is_protected or not repo.requires_reviews:
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="github",
                        severity="CRITICAL",
                        title="Critical repo branch protection insufficient",
                        details_json=json.dumps(
                            {
                                "repo_name": repo.repo_name,
                                "is_protected": repo.is_protected,
                                "requires_reviews": repo.requires_reviews,
                            }
                        ),
                        status="OPEN",
                        created_at=now,
                    )
                )
            if not repo.required_checks_enabled:
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="github",
                        severity="HIGH",
                        title="Critical repo missing required checks",
                        details_json=json.dumps({"repo_name": repo.repo_name}),
                        status="OPEN",
                        created_at=now,
                    )
                )

    if clickup_time:
        tasks = (
            await db.execute(
                select(ClickUpTaskSnapshot).where(
                    ClickUpTaskSnapshot.organization_id == org_id,
                    ClickUpTaskSnapshot.synced_at == clickup_time,
                )
            )
        ).scalars().all()
        for t in tasks:
            tags = {x.strip().lower() for x in json.loads(t.tags or "[]")}
            if "ceo-priority" not in tags and "critical systems" not in (t.name or "").lower():
                continue
            due = t.due_date
            if due and due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due and (now - due) > timedelta(days=7) and (t.status or "").lower() not in {"done", "complete", "closed"}:
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="clickup",
                        severity="CRITICAL",
                        title="Critical task overdue > 7 days",
                        details_json=json.dumps({"task_id": t.external_id, "name": t.name}),
                        status="OPEN",
                        created_at=now,
                    )
                )
            assignees = json.loads(t.assignees or "[]")
            if not assignees or not t.due_date:
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="clickup",
                        severity="MED",
                        title="Critical task missing owner or due date",
                        details_json=json.dumps({"task_id": t.external_id, "name": t.name}),
                        status="OPEN",
                        created_at=now,
                    )
                )

    if do_team_time:
        members = (
            await db.execute(
                select(DigitalOceanTeamSnapshot).where(
                    DigitalOceanTeamSnapshot.organization_id == org_id,
                    DigitalOceanTeamSnapshot.synced_at == do_team_time,
                )
            )
        ).scalars().all()
        for m in members:
            if (m.role or "").lower() == "owner" and m.email.lower() not in _owner_emails():
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="digitalocean",
                        severity="CRITICAL",
                        title="Unauthorized DigitalOcean owner",
                        details_json=json.dumps({"email": m.email, "role": m.role}),
                        status="OPEN",
                        created_at=now,
                    )
                )

    if do_droplet_time:
        droplets = (
            await db.execute(
                select(DigitalOceanDropletSnapshot).where(
                    DigitalOceanDropletSnapshot.organization_id == org_id,
                    DigitalOceanDropletSnapshot.synced_at == do_droplet_time,
                )
            )
        ).scalars().all()
        for d in droplets:
            if d.status == "active" and d.backups_enabled is False:
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="digitalocean",
                        severity="HIGH",
                        title="Active droplet backups disabled",
                        details_json=json.dumps({"droplet_id": d.droplet_id, "name": d.name}),
                        status="OPEN",
                        created_at=now,
                    )
                )

    for v in violations:
        db.add(v)
    # Clean up violations that weren't re-created (resolved on their own)
    await db.execute(
        delete(PolicyViolation).where(PolicyViolation.organization_id == org_id, PolicyViolation.status == "STALE")
    )
    await db.commit()

    score = max(0, 100 - sum(_severity_weight(v.severity) for v in violations))
    return {
        "compliance_score": score,
        "violations": [
            {
                "platform": v.platform,
                "severity": v.severity,
                "title": v.title,
                "details": json.loads(v.details_json),
                "status": v.status,
            }
            for v in violations
        ],
    }


async def latest_report(db: AsyncSession, org_id: int) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(PolicyViolation)
            .where(PolicyViolation.organization_id == org_id)
            .order_by(PolicyViolation.created_at.desc())
            .limit(200)
        )
    ).scalars().all()
    result = []
    for row in rows:
        result.append(
            {
                "platform": row.platform,
                "severity": row.severity,
                "title": row.title,
                "details": json.loads(row.details_json or "{}"),
                "status": row.status,
                "created_at": row.created_at.isoformat(),
            }
        )
    return {"count": len(result), "violations": result}
