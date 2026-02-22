from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.audit import record_action
from app.models.approval import Approval
from app.services import execution as execution_service
from app.tools.calendar import build_calendar_digest


def _handler_assign_leads(payload: dict) -> dict:
    count = int(payload.get("count", 0))
    return {"action": "assign_leads", "assigned_count": count}


def _handler_spend(payload: dict) -> dict:
    if payload.get("force_fail"):
        raise ValueError("Requested failure by payload flag")
    amount = float(payload.get("amount", 0))
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    return {"action": "spend", "approved_amount": amount}


HANDLERS = {
    "assign_leads": _handler_assign_leads,
    "spend": _handler_spend,
    "spend_money": _handler_spend,
    "fetch_calendar_digest": build_calendar_digest,
    "assign_task": lambda payload: {"action": "assign_task", "task_id": payload.get("task_id")},
    "change_crm_status": lambda payload: {"action": "change_crm_status", "lead_id": payload.get("lead_id")},
}


async def execute_approval(
    db: AsyncSession,
    approval: Approval,
    actor_user_id: int,
    actor_org_id: int | None = None,
) -> None:
    # Defence-in-depth: verify the approval belongs to the actor's org when provided.
    if actor_org_id is not None and approval.organization_id != actor_org_id:
        raise ValueError(
            f"Cross-org execution denied: approval org {approval.organization_id} "
            f"!= actor org {actor_org_id}"
        )
    execution = await execution_service.create_execution(
        db,
        organization_id=approval.organization_id,
        approval_id=approval.id,
        triggered_by=actor_user_id,
        status="running",
    )
    await record_action(
        db,
        event_type="execution_started",
        actor_user_id=actor_user_id,
        organization_id=approval.organization_id,
        entity_type="execution",
        entity_id=execution.id,
        payload_json={"approval_id": approval.id, "approval_type": approval.approval_type},
    )

    # send_message is handled async via email_service to actually dispatch Gmail
    if approval.approval_type == "send_message":
        try:
            from app.services.email_service import send_approved_compose, send_approved_reply

            payload = approval.payload_json or {}
            email_id = payload.get("email_id")
            if email_id:
                sent = await send_approved_reply(
                    db=db,
                    email_id=int(email_id),
                    org_id=approval.organization_id,
                    actor_user_id=actor_user_id,
                )
                mode = "reply"
            else:
                sent = await send_approved_compose(
                    db=db,
                    approval=approval,
                    org_id=approval.organization_id,
                    actor_user_id=actor_user_id,
                )
                mode = "compose"
            output = {"action": "send_message", "mode": mode, "sent": sent}
            status = "succeeded" if sent else "failed"
            error_text = None if sent else "Gmail send returned False"
            await execution_service.complete_execution(
                db, execution.id, status=status, output_json=output,
                error_text=error_text,
            )
            await record_action(
                db,
                event_type=f"execution_{status}",
                actor_user_id=actor_user_id,
                organization_id=approval.organization_id,
                entity_type="execution",
                entity_id=execution.id,
                payload_json={"approval_id": approval.id, "output": output},
            )
        except Exception as exc:
            await execution_service.complete_execution(
                db, execution.id, status="failed", error_text=str(exc),
            )
            await record_action(
                db,
                event_type="execution_failed",
                actor_user_id=actor_user_id,
                organization_id=approval.organization_id,
                entity_type="execution",
                entity_id=execution.id,
                payload_json={"approval_id": approval.id, "error": str(exc)},
            )
        return

    handler = HANDLERS.get(approval.approval_type)
    if handler is None:
        await execution_service.complete_execution(
            db,
            execution.id,
            status="skipped",
            output_json={"reason": "no_handler"},
        )
        await record_action(
            db,
            event_type="execution_skipped",
            actor_user_id=actor_user_id,
            organization_id=approval.organization_id,
            entity_type="execution",
            entity_id=execution.id,
            payload_json={"approval_type": approval.approval_type},
        )
        return

    try:
        output = handler(approval.payload_json or {})
        await execution_service.complete_execution(
            db,
            execution.id,
            status="succeeded",
            output_json=output,
        )
        await record_action(
            db,
            event_type="execution_succeeded",
            actor_user_id=actor_user_id,
            organization_id=approval.organization_id,
            entity_type="execution",
            entity_id=execution.id,
            payload_json={"approval_id": approval.id, "output": output},
        )
    except Exception as exc:
        await execution_service.complete_execution(
            db,
            execution.id,
            status="failed",
            error_text=str(exc),
        )
        await record_action(
            db,
            event_type="execution_failed",
            actor_user_id=actor_user_id,
            organization_id=approval.organization_id,
            entity_type="execution",
            entity_id=execution.id,
            payload_json={"approval_id": approval.id, "error": str(exc)},
        )
