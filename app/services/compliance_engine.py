from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ceo_control import (
    ClickUpTaskSnapshot,
    DigitalOceanCostSnapshot,
    DigitalOceanDropletSnapshot,
    DigitalOceanTeamSnapshot,
    GitHubIdentityMap,
    GitHubRepoSnapshot,
    GitHubRoleSnapshot,
    OrgPerson,
    PolicyViolation,
)
from app.services import integration as integration_service
from app.tools import github_admin

logger = logging.getLogger(__name__)


def _owner_emails() -> set[str]:
    return {e.strip().lower() for e in settings.COMPLIANCE_OWNER_EMAILS.split(",") if e.strip()}


def _dev_emails() -> set[str]:
    return {e.strip().lower() for e in settings.COMPLIANCE_DEV_EMAILS.split(",") if e.strip()}


def _company_domain() -> str:
    return (settings.COMPLIANCE_COMPANY_DOMAIN or "").strip().lower()


def _allowed_personal_emails() -> set[str]:
    return {
        e.strip().lower()
        for e in (settings.COMPLIANCE_ALLOWED_PERSONAL_EMAILS or "").split(",")
        if e.strip()
    }


def _is_company_email(email: str | None) -> bool:
    if not email:
        return False
    domain = _company_domain()
    if not domain:
        return False
    value = email.strip().lower()
    return value.endswith(f"@{domain}")


def _is_personal_org(org_id: int) -> bool:
    return settings.PERSONAL_ORG_ID is not None and org_id == settings.PERSONAL_ORG_ID


def _is_authorized_owner_email(email: str | None) -> bool:
    normalized = (email or "").strip().lower()
    if not normalized:
        return False
    if normalized in _owner_emails():
        return True
    return bool(
        settings.COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS
        and normalized in _allowed_personal_emails()
    )


def _critical_repos() -> set[str]:
    raw = settings.CRITICAL_GITHUB_REPOS or ""
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _repo_is_critical(repo_name: str | None) -> bool:
    if not repo_name:
        return False
    critical = _critical_repos()
    if not critical:
        return True
    normalized = repo_name.strip().lower()
    short = normalized.split("/")[-1]
    return normalized in critical or short in critical


def _now() -> datetime:
    return datetime.now(UTC)


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
    personal_org = _is_personal_org(org_id)
    if not personal_org:
        await ensure_company_directory(db, org_id)

    # Mark existing OPEN violations as stale; will be refreshed below
    from sqlalchemy import update
    await db.execute(
        update(PolicyViolation)
        .where(PolicyViolation.organization_id == org_id, PolicyViolation.status == "OPEN")
        .values(status="STALE")
    )

    identity_rows = (
        await db.execute(select(GitHubIdentityMap).where(GitHubIdentityMap.organization_id == org_id).limit(5000))
    ).scalars().all()
    login_to_email = {row.github_login.lower(): row.company_email.lower() for row in identity_rows}
    allowed_personal = _allowed_personal_emails()

    violations: list[PolicyViolation] = []
    github_personal_identity_seen: set[tuple[str, str]] = set()
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
        unmapped_logins: set[str] = set()
        critical_repo_roles = [r for r in roles if _repo_is_critical(r.repo_name)]
        for r in roles:
            email = login_to_email.get((r.github_login or "").lower())
            if (not personal_org) and (r.github_login or "").strip() and not email:
                unmapped_logins.add((r.github_login or "").strip())
            if (
                not personal_org
                and email
                and not _is_company_email(email)
                and email not in allowed_personal
            ):
                key = ((r.github_login or "").lower(), email)
                if key not in github_personal_identity_seen:
                    github_personal_identity_seen.add(key)
                    violations.append(
                        PolicyViolation(
                            organization_id=org_id,
                            platform="github",
                            severity="MED",
                            title="Personal email mapped to company GitHub identity",
                            details_json=json.dumps(
                                {"github_login": r.github_login, "mapped_email": email}
                            ),
                            status="OPEN",
                            created_at=now,
                        )
                    )
            if (
                not personal_org
                and (r.org_role or "").lower() == "owner"
                and not _is_authorized_owner_email(email)
            ):
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
        if not personal_org and unmapped_logins:
            for login in sorted(unmapped_logins)[:20]:
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="github",
                        severity="MED",
                        title="GitHub identity mapping missing",
                        details_json=json.dumps({"github_login": login}),
                        status="OPEN",
                        created_at=now,
                    )
                )
        if not personal_org and critical_repo_roles:
            tech_lead_email = (settings.COMPLIANCE_TECH_LEAD_EMAIL or "").strip().lower()
            ops_manager_email = (settings.COMPLIANCE_OPS_MANAGER_EMAIL or "").strip().lower()
            tech_logins = {
                login for login, mapped in login_to_email.items() if mapped == tech_lead_email
            }
            ops_logins = {
                login for login, mapped in login_to_email.items() if mapped == ops_manager_email
            }

            if not tech_logins:
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="github",
                        severity="HIGH",
                        title="Tech lead GitHub identity mapping missing",
                        details_json=json.dumps({"expected_email": tech_lead_email}),
                        status="OPEN",
                        created_at=now,
                    )
                )
            else:
                by_repo_ops: dict[str, list[GitHubRoleSnapshot]] = {}
                for role in critical_repo_roles:
                    if not role.repo_name:
                        continue
                    by_repo_ops.setdefault(role.repo_name.lower(), []).append(role)
                for repo_name, repo_roles in by_repo_ops.items():
                    if not any(
                        (x.github_login or "").lower() in tech_logins
                        and (x.repo_permission or "").lower() in {"maintain", "admin"}
                        for x in repo_roles
                    ):
                        violations.append(
                            PolicyViolation(
                                organization_id=org_id,
                                platform="github",
                                severity="HIGH",
                                title="Tech lead lacks maintain/admin on critical repo",
                                details_json=json.dumps({"repo_name": repo_name, "expected_email": tech_lead_email}),
                                status="OPEN",
                                created_at=now,
                            )
                        )
            if ops_logins:
                by_repo: dict[str, list[GitHubRoleSnapshot]] = {}
                for role in critical_repo_roles:
                    if not role.repo_name:
                        continue
                    by_repo.setdefault(role.repo_name.lower(), []).append(role)
                for repo_name, repo_roles in by_repo.items():
                    if not any(
                        (x.github_login or "").lower() in ops_logins
                        and (x.repo_permission or "").lower() in {"read", "write", "maintain", "admin"}
                        for x in repo_roles
                    ):
                        violations.append(
                            PolicyViolation(
                                organization_id=org_id,
                                platform="github",
                                severity="MED",
                                title="Ops manager lacks visibility on critical repo PR queue",
                                details_json=json.dumps({"repo_name": repo_name, "expected_email": ops_manager_email}),
                                status="OPEN",
                                created_at=now,
                            )
                        )
            dev_emails = _dev_emails()
            for cr in critical_repo_roles:
                cr_email = login_to_email.get((cr.github_login or "").lower())
                if (
                    cr_email
                    and cr_email in dev_emails
                    and (cr.repo_permission or "").lower() in {"admin", "maintain"}
                ):
                    violations.append(
                        PolicyViolation(
                            organization_id=org_id,
                            platform="github",
                            severity="CRITICAL",
                            title="Developer has elevated repo permission",
                            details_json=json.dumps(
                                {
                                    "github_login": cr.github_login,
                                    "repo_name": cr.repo_name,
                                    "repo_permission": cr.repo_permission,
                                }
                            ),
                            status="OPEN",
                            created_at=now,
                        )
                    )

    if not personal_org and (settings.GITHUB_ORG or "").strip():
        github_integration = await integration_service.get_integration_by_type(db, org_id, "github")
        github_token = ((github_integration.config_json or {}).get("access_token") if github_integration else None)
        if isinstance(github_token, str) and github_token.strip():
            try:
                invitations = await github_admin.list_org_invitations(
                    github_token,
                    (settings.GITHUB_ORG or "").strip(),
                )
            except (TimeoutError, ConnectionError, ValueError) as exc:
                logger.warning("Failed to list GitHub org invitations: %s", type(exc).__name__)
                invitations = []
            seen_owner_invites: set[tuple[str, str, str]] = set()
            for invite in invitations:
                invite_role = str(invite.get("role") or "").strip().lower()
                if invite_role not in {"admin", "owner"}:
                    continue
                inviter_login = str((invite.get("inviter") or {}).get("login") or "").strip().lower()
                invitee_email = str(invite.get("email") or "").strip().lower()
                inviter_email = login_to_email.get(inviter_login, "")
                if _is_authorized_owner_email(inviter_email):
                    continue
                dedupe_key = (inviter_login, invitee_email, invite_role)
                if dedupe_key in seen_owner_invites:
                    continue
                seen_owner_invites.add(dedupe_key)
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="github",
                        severity="HIGH",
                        title="GitHub owner invitation created by non-owner",
                        details_json=json.dumps(
                            {
                                "inviter_login": inviter_login,
                                "inviter_mapped_email": inviter_email or None,
                                "invitee_email": invitee_email or None,
                                "invitation_role": invite_role,
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
            if not _repo_is_critical(repo.repo_name):
                continue
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
                due = due.replace(tzinfo=UTC)
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
            updated = t.updated_at_remote
            if updated and updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if "block" in (t.status or "").lower() and updated and (now - updated) > timedelta(days=3):
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="clickup",
                        severity="HIGH",
                        title="Blocked critical task > 3 days",
                        details_json=json.dumps({"task_id": t.external_id, "name": t.name, "status": t.status}),
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
            normalized_email = (m.email or "").strip().lower()
            if (
                not personal_org
                and normalized_email
                and not _is_company_email(normalized_email)
                and normalized_email not in allowed_personal
            ):
                violations.append(
                    PolicyViolation(
                        organization_id=org_id,
                        platform="digitalocean",
                        severity="MED",
                        title="Personal email present in company infra access",
                        details_json=json.dumps({"email": normalized_email, "role": m.role}),
                        status="OPEN",
                        created_at=now,
                    )
                )
            if (
                not personal_org
                and (m.role or "").lower() == "owner"
                and not _is_authorized_owner_email(normalized_email)
            ):
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
            if d.status == "active" and not d.backups_enabled:
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
    recent_costs = (
        await db.execute(
            select(DigitalOceanCostSnapshot)
            .where(
                DigitalOceanCostSnapshot.organization_id == org_id,
                DigitalOceanCostSnapshot.synced_at >= now - timedelta(days=60),
                DigitalOceanCostSnapshot.amount_usd.is_not(None),
            )
            .order_by(DigitalOceanCostSnapshot.synced_at.desc())
        )
    ).scalars().all()
    if len(recent_costs) >= 4:
        recent_window = [
            float(c.amount_usd)
            for c in recent_costs
            if c.synced_at >= now - timedelta(days=30) and c.amount_usd is not None
        ]
        previous_window = [
            float(c.amount_usd)
            for c in recent_costs
            if (now - timedelta(days=60)) <= c.synced_at < (now - timedelta(days=30))
            and c.amount_usd is not None
        ]
        if recent_window and previous_window:
            recent_avg = sum(recent_window) / len(recent_window)
            previous_avg = sum(previous_window) / len(previous_window)
            if previous_avg > 0:
                delta_pct = ((recent_avg - previous_avg) / previous_avg) * 100.0
                if delta_pct > 30:
                    violations.append(
                        PolicyViolation(
                            organization_id=org_id,
                            platform="digitalocean",
                            severity="MED",
                            title="DigitalOcean cost spike > 30% vs previous 30 days",
                            details_json=json.dumps(
                                {
                                    "recent_avg_usd": round(recent_avg, 2),
                                    "previous_avg_usd": round(previous_avg, 2),
                                    "delta_percent": round(delta_pct, 1),
                                }
                            ),
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
