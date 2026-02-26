"""Compliance run, report, and message drafting endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.core.request_context import get_current_request_id
from app.logs.audit import record_action
from app.schemas.control import (
    ComplianceReportRead,
    ComplianceRunRead,
    MessageDraftRead,
    MessageDraftRequest,
)
from app.services import compliance_engine

router = APIRouter()


@router.post("/compliance/run", response_model=ComplianceRunRead)
async def compliance_run(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ComplianceRunRead:
    org_id = int(actor["org_id"])
    request_id = get_current_request_id()
    try:
        result = await compliance_engine.run_compliance(db, org_id)
        await record_action(
            db,
            event_type="compliance_run",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="control",
            entity_id=None,
            payload_json={
                "request_id": request_id,
                "status": "ok",
                "violation_count": len(result["violations"]),
                "compliance_score": int(result["compliance_score"]),
            },
        )
        return ComplianceRunRead(ok=True, compliance_score=int(result["compliance_score"]), violations=result["violations"], mode="suggest_only")
    except (RuntimeError, ValueError, TypeError, SQLAlchemyError, TimeoutError, ConnectionError, OSError) as exc:
        await record_action(
            db,
            event_type="compliance_run",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="control",
            entity_id=None,
            payload_json={
                "request_id": request_id,
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise


@router.get("/compliance/report", response_model=ComplianceReportRead)
async def compliance_report(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ComplianceReportRead:
    org_id = int(actor["org_id"])
    data = await compliance_engine.latest_report(db, org_id)
    return ComplianceReportRead(**data)


@router.post("/message-draft", response_model=MessageDraftRead)
async def message_draft(
    payload: MessageDraftRequest,
    _db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MessageDraftRead:
    to = str(payload.to or "").strip().lower()
    topic = str(payload.topic or "Compliance follow-up")
    violations = payload.violations or []

    intro = "Hi Sharon," if to == "sharon" else "Hi Mano,"
    bullet_lines = []
    for item in violations[:8]:
        if isinstance(item, dict):
            bullet_lines.append(f"- {item.get('title', 'Issue')} ({item.get('severity', 'MED')})")
    if not bullet_lines:
        bullet_lines.append("- Please review the latest compliance dashboard.")

    checklist = [
        "Confirm owners/permissions align with company hierarchy.",
        "Acknowledge each open violation with ETA.",
        "Post update in leadership channel after completion.",
    ]
    text = "\n".join(
        [
            intro,
            "",
            f"Topic: {topic}",
            "Please review and action the following:",
            *bullet_lines,
            "",
            "This is suggest-only guidance; no automatic enforcement actions were taken.",
        ]
    )
    return MessageDraftRead(to=to, message=text, checklist=checklist)
