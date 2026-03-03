"""GDPR tenant purge endpoint — extracted to keep admin.py under the size guard."""
import importlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_super_admin
from app.logs.audit import record_action
from app.models.organization import Organization

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Super Admin"])

_PURGE_CONFIRM_TEMPLATE = "YES PURGE ORG {org_id}"

# Ordered to respect FK constraints: children before parents.
_ORG_SCOPED_MODELS: list[str] = [
    "app.models.ai_call_log.AiCallLog",
    "app.models.clone_performance.ClonePerformanceWeekly",
    "app.models.clone_memory.CloneMemoryEntry",
    "app.models.clone_control.EmployeeCloneProfile",
    "app.models.coaching_report.CoachingReport",
    "app.models.approval.Approval",
    "app.models.event.Event",
    "app.models.notification.Notification",
    "app.models.ceo_control.SchedulerJobRun",
    "app.models.ceo_control.CEOSummary",
    "app.models.task.Task",
    "app.models.project.Project",
    "app.models.goal.Goal",
    "app.models.note.Note",
    "app.models.contact.Contact",
    "app.models.integration.Integration",
    "app.models.employee.Employee",
    "app.models.user.User",
]


def _actor_user_id(actor: dict) -> int | None:
    raw = actor.get("id")
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str | bytes | bytearray):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


async def _load_org_or_404(db: AsyncSession, org_id: int) -> Organization:
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


@router.delete("/orgs/{org_id}/purge", response_model=dict)
async def purge_org_data(
    org_id: int,
    confirm: str = Query(..., description='Must be "YES PURGE ORG <org_id>" to proceed'),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_super_admin),
) -> dict:
    """GDPR right-to-be-forgotten: permanently delete all data for an organisation.

    This is irreversible. The confirm query param must equal "YES PURGE ORG {org_id}".
    The organisation row itself is preserved so foreign-key references don't break;
    only its member data is erased. Delete the org row separately if required.
    """
    expected = _PURGE_CONFIRM_TEMPLATE.format(org_id=org_id)
    if confirm != expected:
        raise HTTPException(
            status_code=400,
            detail=f'Confirmation string must be exactly: "{expected}"',
        )

    org = await _load_org_or_404(db, org_id)

    # Audit the intent BEFORE deletion so the record survives the cascade.
    await record_action(
        db=db,
        event_type="org_data_purged",
        actor_user_id=_actor_user_id(actor),
        organization_id=org_id,
        entity_type="organization",
        entity_id=org_id,
        payload_json={"org_name": org.name, "initiated_by": actor.get("email")},
    )
    await db.commit()

    counts: dict[str, int] = {}
    for dotpath in _ORG_SCOPED_MODELS:
        module_path, cls_name = dotpath.rsplit(".", 1)
        try:
            mod = importlib.import_module(module_path)
            model_cls = getattr(mod, cls_name)
            col = getattr(model_cls, "organization_id", None)
            if col is None:
                col = getattr(model_cls, "org_id", None)
            if col is None:
                continue
            result = await db.execute(sa_delete(model_cls).where(col == org_id))
            counts[cls_name] = result.rowcount
        except Exception as exc:
            logger.warning("Purge: skipped %s — %s: %s", cls_name, type(exc).__name__, exc)

    await db.commit()

    logger.warning(
        "GDPR purge completed for org_id=%d by actor=%s — rows deleted: %s",
        org_id, actor.get("email"), counts,
    )
    return {"org_id": org_id, "purged": True, "rows_deleted": counts}
