import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.audit import record_action
from app.models.approval import Approval
from app.services import execution as execution_service
from app.services.email_service import send_approved_compose, send_approved_reply
from app.tools.calendar import build_calendar_digest

logger = logging.getLogger(__name__)

HANDLER_TIMEOUT_SECONDS = 30


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handler_assign_leads(payload: dict[str, Any]) -> dict[str, Any]:
    count = int(payload.get("count", 0))
    return {"action": "assign_leads", "assigned_count": count}


def _handler_spend(payload: dict[str, Any]) -> dict[str, Any]:
    amount = float(payload.get("amount", 0))
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    return {"action": "spend", "approved_amount": amount}


HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "assign_leads": _handler_assign_leads,
    "spend": _handler_spend,
    "spend_money": _handler_spend,
    "fetch_calendar_digest": build_calendar_digest,
    "assign_task": lambda payload: {"action": "assign_task", "task_id": payload.get("task_id")},
    "change_crm_status": lambda payload: {"action": "change_crm_status", "lead_id": payload.get("lead_id")},
}


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _atomic_claim_executed_at(db: AsyncSession, approval_id: int) -> bool:
    """Atomically claim executed_at. Returns True if this caller won the slot."""
    result = await db.execute(
        update(Approval)
        .where(Approval.id == approval_id, Approval.executed_at.is_(None))
        .values(executed_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return bool((result.rowcount or 0) == 1)


async def _run_handler(
    handler: Callable[[dict[str, Any]], Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Run a handler (sync or async) with a timeout, validate return type."""
    if asyncio.iscoroutinefunction(handler) or inspect.isasyncgenfunction(handler):
        result = await asyncio.wait_for(handler(payload), timeout=HANDLER_TIMEOUT_SECONDS)
    else:
        result = handler(payload)
        if asyncio.iscoroutine(result):
            result = await asyncio.wait_for(
                result, timeout=HANDLER_TIMEOUT_SECONDS
            )
    if not isinstance(result, dict):
        raise TypeError(
            f"Handler returned {type(result).__name__}, expected dict"
        )
    return result


async def _finalize_execution(
    db: AsyncSession,
    execution_id: int,
    approval_id: int,
    actor_user_id: int,
    organization_id: int,
    status: str,
    output: dict | None = None,
    error_text: str | None = None,
) -> None:
    """Complete execution record + audit log. Errors here are logged, not raised."""
    try:
        await execution_service.complete_execution(
            db, execution_id, status=status,
            output_json=output, error_text=error_text,
        )
        await record_action(
            db,
            event_type=f"execution_{status}",
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            entity_type="execution",
            entity_id=execution_id,
            payload_json={"approval_id": approval_id, "output": output or {}},
        )
    except Exception:
        logger.exception(
            "Failed to finalize execution %d for approval %d",
            execution_id, approval_id,
        )


# ── Main entry point ─────────────────────────────────────────────────────────

async def execute_approval(
    db: AsyncSession,
    approval: Approval,
    actor_user_id: int,
    actor_org_id: int,
) -> None:
    # Org isolation check
    if approval.organization_id != actor_org_id:
        raise ValueError(
            f"Cross-org execution denied: approval org {approval.organization_id} "
            f"!= actor org {actor_org_id}"
        )

    # Status guard: only approved approvals can be executed
    if approval.status != "approved":
        raise ValueError(
            f"Cannot execute approval {approval.id} with status '{approval.status}'"
        )

    # Double-execution guard
    if approval.executed_at is not None:
        logger.warning(
            "Approval %d already executed at %s — skipping",
            approval.id, approval.executed_at,
        )
        return

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

    # ── Email path (email_service does its own atomic executed_at claim) ──
    if approval.approval_type == "send_message":
        try:
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
            await _finalize_execution(
                db, execution.id, approval.id,
                actor_user_id, approval.organization_id,
                status=status, output=output, error_text=error_text,
            )
        except Exception as exc:
            _err = f"{type(exc).__name__}: {str(exc)[:200]}"
            await _finalize_execution(
                db, execution.id, approval.id,
                actor_user_id, approval.organization_id,
                status="failed", error_text=_err,
            )
        return

    # ── Generic handler path ──
    handler = HANDLERS.get(approval.approval_type)
    if handler is None:
        await _finalize_execution(
            db, execution.id, approval.id,
            actor_user_id, approval.organization_id,
            status="skipped", output={"reason": "no_handler"},
        )
        return

    try:
        output = await _run_handler(handler, approval.payload_json or {})
        claimed = await _atomic_claim_executed_at(db, approval.id)
        if not claimed:
            logger.warning("Approval %d already claimed by concurrent request", approval.id)
            await _finalize_execution(
                db, execution.id, approval.id,
                actor_user_id, approval.organization_id,
                status="skipped", output={"reason": "already_executed"},
            )
            return
        await _finalize_execution(
            db, execution.id, approval.id,
            actor_user_id, approval.organization_id,
            status="succeeded", output=output,
        )
    except asyncio.TimeoutError:
        await _finalize_execution(
            db, execution.id, approval.id,
            actor_user_id, approval.organization_id,
            status="failed",
            error_text=f"Handler '{approval.approval_type}' timed out after {HANDLER_TIMEOUT_SECONDS}s",
        )
    except Exception as exc:
        _err = f"{type(exc).__name__}: {str(exc)[:200]}"
        await _finalize_execution(
            db, execution.id, approval.id,
            actor_user_id, approval.organization_id,
            status="failed", error_text=_err,
        )
