from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.approval import Approval
from app.models.email import Email
from app.models.task import Task
from app.schemas.approval import ApprovalRequestCreate
from app.schemas.task import TaskCreate
from app.services import email_service
from app.services.approval import request_approval
from app.services.task import create_task

_REPORT_REQUIRED_FIELDS = ("owner", "date", "completed", "planned", "blockers")
_ACTION_KEYWORDS = ("action required", "please", "follow up", "deadline", "todo", "next steps")
_APPROVAL_KEYWORDS = ("approval", "approve", "permission", "sign off", "yes execute")
_ESCALATION_KEYWORDS = ("urgent", "escalate", "blocked", "incident", "outage", "critical")


class _ControlItem(TypedDict):
    email_id: int
    classification: str
    confidence: float
    task_id: int | None
    approval_id: int | None
    notes: list[str]


class _PendingDigest(TypedDict):
    org_id: int
    generated_at: str
    total_open_tasks: int
    total_pending_approvals: int
    lines: list[str]


def manager_report_template() -> dict[str, object]:
    prefix = settings.EMAIL_CONTROL_REPORT_SUBJECT_PREFIX
    markdown = (
        f"Subject: {prefix} TeamName - YYYY-MM-DD\n\n"
        "Owner: name@company.com\n"
        "Date: YYYY-MM-DD\n"
        "Completed:\n"
        "- ...\n"
        "Planned:\n"
        "- ...\n"
        "Blockers:\n"
        "- ...\n"
    )
    return {
        "subject_prefix": prefix,
        "required_fields": list(_REPORT_REQUIRED_FIELDS),
        "markdown_template": markdown,
    }


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in keywords)


def _is_manager_report(email: Email) -> bool:
    subject = (email.subject or "").strip().lower()
    prefix = (settings.EMAIL_CONTROL_REPORT_SUBJECT_PREFIX or "[REPORT]").strip().lower()
    return subject.startswith(prefix.lower()) or "daily report" in subject or "weekly report" in subject


def _manager_report_missing_fields(body_text: str | None) -> list[str]:
    text = (body_text or "").lower()
    missing = [field for field in _REPORT_REQUIRED_FIELDS if f"{field}:" not in text]
    return missing


def _classify_email(email: Email) -> tuple[str, float, list[str]]:
    subject = email.subject or ""
    body = email.body_text or ""
    combined = f"{subject}\n{body}"
    notes: list[str] = []

    if _is_manager_report(email):
        missing = _manager_report_missing_fields(body)
        if missing:
            notes.append(f"Manager report missing fields: {', '.join(missing)}")
            return ("action", 0.85, notes)
        return ("fyi", 0.95, ["Manager report matched standard format."])
    if _contains_any(combined, _ESCALATION_KEYWORDS):
        return ("escalation", 0.9, notes)
    if _contains_any(combined, _APPROVAL_KEYWORDS):
        return ("approval", 0.88, notes)
    if _contains_any(combined, _ACTION_KEYWORDS):
        return ("action", 0.8, notes)
    return ("fyi", 0.7, notes)


async def _find_existing_task_for_email(db: AsyncSession, org_id: int, email_id: int) -> Task | None:
    result = await db.execute(
        select(Task).where(
            Task.organization_id == org_id,
            Task.external_source == "email_control",
            Task.external_id == f"email:{email_id}",
        )
    )
    return cast(Task | None, result.scalar_one_or_none())


async def _create_task_from_email(
    db: AsyncSession,
    *,
    email: Email,
    org_id: int,
    escalation: bool,
) -> int | None:
    existing = await _find_existing_task_for_email(db, org_id, email.id)
    if existing is not None:
        return cast(int, existing.id)
    owner = (email.from_address or "unknown@sender").strip()
    title_prefix = "[Escalation] " if escalation else "[Action] "
    task = await create_task(
        db=db,
        organization_id=org_id,
        data=TaskCreate(
            title=f"{title_prefix}{(email.subject or 'Email follow-up').strip()}",
            description=(
                f"Source email id: {email.id}\n"
                f"Owner: {owner}\n"
                f"From: {email.from_address or '-'}\n"
                f"Subject: {email.subject or '-'}\n"
                f"Thread: {email.thread_id or '-'}"
            ),
            category="business",
            priority=4 if escalation else 3,
        ),
    )
    task.external_source = "email_control"
    task.external_id = f"email:{email.id}"
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return cast(int, task.id)


async def _ensure_approval_draft(
    db: AsyncSession,
    *,
    email: Email,
    org_id: int,
    actor_user_id: int,
) -> int | None:
    if email.approval_id:
        return cast(int, email.approval_id)
    draft = await email_service.draft_reply(
        db=db,
        email_id=email.id,
        org_id=org_id,
        actor_user_id=actor_user_id,
        instruction="Prepare concise action-oriented response for approval.",
    )
    if not draft:
        return None
    refreshed = await email_service.get_email(db, email.id, org_id)
    return refreshed.approval_id if refreshed else None


async def process_inbox_controls(
    db: AsyncSession,
    *,
    org_id: int,
    actor_user_id: int,
    limit: int = 50,
) -> dict[str, object]:
    rows = (
        await db.execute(
            select(Email)
            .where(Email.organization_id == org_id)
            .order_by(Email.received_at.desc(), Email.id.desc())
            .limit(max(1, min(limit, 200)))
        )
    ).scalars().all()

    tasks_created = 0
    approvals_created = 0
    drafts_created = 0
    escalations_flagged = 0
    processed = 0
    items: list[_ControlItem] = []

    for email in rows:
        classification, confidence, notes = _classify_email(email)
        task_id: int | None = None
        approval_id: int | None = None

        if classification in {"action", "escalation"}:
            before = await _find_existing_task_for_email(db, org_id, email.id)
            task_id = await _create_task_from_email(
                db=db,
                email=email,
                org_id=org_id,
                escalation=(classification == "escalation"),
            )
            if before is None and task_id is not None:
                tasks_created += 1
            if classification == "escalation":
                escalations_flagged += 1
        elif classification == "approval":
            existing_approval = email.approval_id
            approval_id = await _ensure_approval_draft(
                db=db,
                email=email,
                org_id=org_id,
                actor_user_id=actor_user_id,
            )
            if approval_id and not existing_approval:
                approvals_created += 1
                drafts_created += 1

        email.category = classification
        db.add(email)
        processed += 1
        items.append(
            {
                "email_id": email.id,
                "classification": classification,
                "confidence": confidence,
                "task_id": task_id,
                "approval_id": approval_id,
                "notes": notes,
            }
        )

    await db.commit()
    return {
        "scanned": len(rows),
        "processed": processed,
        "tasks_created": tasks_created,
        "approvals_created": approvals_created,
        "drafts_created": drafts_created,
        "escalations_flagged": escalations_flagged,
        "items": items,
    }


def _extract_owner_from_task(task: Task) -> str:
    desc = task.description or ""
    for line in desc.splitlines():
        if line.lower().startswith("owner:"):
            return line.split(":", 1)[1].strip() or "unassigned"
    return "unassigned"


async def build_pending_actions_digest(
    db: AsyncSession,
    *,
    org_id: int,
) -> _PendingDigest:
    open_tasks = (
        await db.execute(
            select(Task).where(Task.organization_id == org_id, Task.is_done.is_(False))
            .order_by(Task.priority.desc(), Task.created_at.desc())
            .limit(500)
        )
    ).scalars().all()
    pending_approvals = (
        await db.execute(
            select(Approval).where(
                Approval.organization_id == org_id,
                Approval.status == "pending",
            ).order_by(Approval.created_at.desc())
            .limit(500)
        )
    ).scalars().all()

    owners: dict[str, dict[str, int]] = {}
    for task in open_tasks:
        owner = _extract_owner_from_task(task)
        owners.setdefault(owner, {"tasks": 0, "approvals": 0})
        owners[owner]["tasks"] += 1
    for appr in pending_approvals:
        owner = f"user:{appr.requested_by}"
        owners.setdefault(owner, {"tasks": 0, "approvals": 0})
        owners[owner]["approvals"] += 1

    lines = [
        f"- {owner}: {data['tasks']} open task(s), {data['approvals']} pending approval(s)"
        for owner, data in sorted(owners.items(), key=lambda kv: (kv[1]["tasks"] + kv[1]["approvals"]), reverse=True)
    ]
    if not lines:
        lines = ["- No pending owner actions."]

    return {
        "org_id": org_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_open_tasks": len(open_tasks),
        "total_pending_approvals": len(pending_approvals),
        "lines": lines,
    }


async def draft_pending_actions_digest_email(
    db: AsyncSession,
    *,
    org_id: int,
    actor_user_id: int,
) -> dict[str, object]:
    digest: _PendingDigest = await build_pending_actions_digest(db, org_id=org_id)
    to_addr = (settings.EMAIL_CONTROL_DIGEST_TO or settings.ADMIN_EMAIL).strip()
    subject = f"[Daily Pending Actions] Org {org_id} - {datetime.now(UTC).date().isoformat()}"
    body = "\n".join(
        [
            "Daily owner-wise pending actions summary:",
            "",
            *[str(x) for x in digest["lines"]],
            "",
            "This draft is generated automatically and requires approval before sending.",
        ]
    )
    approval = await request_approval(
        db=db,
        requested_by=actor_user_id,
        data=ApprovalRequestCreate(
            organization_id=org_id,
            approval_type="send_message",
            payload_json={
                "compose": True,
                "to": to_addr,
                "subject": subject,
                "draft_body": body,
                "source": "email_control_digest",
                "digest_generated_at": digest["generated_at"],
            },
        ),
    )
    return {
        "ok": True,
        "approval_id": approval.id,
        "to": to_addr,
        "subject": subject,
        "preview": body[:300],
    }
