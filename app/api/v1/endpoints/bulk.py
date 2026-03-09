"""Bulk operations — CSV import, batch delete, batch update."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.services import bulk_operations

router = APIRouter(prefix="/bulk", tags=["Bulk Operations"])


@router.post("/import/contacts")
async def import_contacts(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Import contacts from a CSV file. Columns: name, email, phone, company, role, relationship, pipeline_stage, tags."""
    content = await file.read()
    csv_text = content.decode("utf-8-sig")
    result = await bulk_operations.import_contacts_csv(db, organization_id=actor["org_id"], csv_text=csv_text)
    await record_action(
        db, event_type="bulk_import_contacts", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="contact", entity_id=None,
        payload_json={"imported": result["imported"], "skipped": result["skipped"]},
    )
    return result


@router.post("/import/tasks")
async def import_tasks(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Import tasks from a CSV file. Columns: title, description, priority, category, due_date, project_id."""
    content = await file.read()
    csv_text = content.decode("utf-8-sig")
    result = await bulk_operations.import_tasks_csv(db, organization_id=actor["org_id"], csv_text=csv_text)
    await record_action(
        db, event_type="bulk_import_tasks", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="task", entity_id=None,
        payload_json={"imported": result["imported"], "skipped": result["skipped"]},
    )
    return result


@router.post("/import/deals")
async def import_deals(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Import deals from a CSV file. Columns: title, value, stage, probability, expected_close_date, contact_id, description, source."""
    content = await file.read()
    csv_text = content.decode("utf-8-sig")
    result = await bulk_operations.import_deals_csv(db, organization_id=actor["org_id"], csv_text=csv_text)
    await record_action(
        db, event_type="bulk_import_deals", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="deal", entity_id=None,
        payload_json={"imported": result["imported"], "skipped": result["skipped"]},
    )
    return result


class BatchDeleteRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=500)


@router.post("/contacts/delete")
async def batch_delete_contacts(
    data: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Delete multiple contacts by ID."""
    result = await bulk_operations.batch_delete_contacts(db, organization_id=actor["org_id"], contact_ids=data.ids)
    await record_action(
        db, event_type="bulk_delete_contacts", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="contact", entity_id=None,
        payload_json=result,
    )
    return result


class BatchStageRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=500)
    pipeline_stage: str


@router.post("/contacts/update-stage")
async def batch_update_stage(
    data: BatchStageRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    """Move multiple contacts to a pipeline stage."""
    result = await bulk_operations.batch_update_contacts_stage(
        db, organization_id=actor["org_id"],
        contact_ids=data.ids, pipeline_stage=data.pipeline_stage,
    )
    await record_action(
        db, event_type="bulk_update_contacts_stage", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="contact", entity_id=None,
        payload_json={"count": len(data.ids), "stage": data.pipeline_stage},
    )
    return result
