"""Media upload, management, and AI-powered analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.services import media_agent, media_storage

router = APIRouter(prefix="/media", tags=["Media"])


def _attachment_to_dict(att) -> dict:
    return {
        "id": att.id,
        "file_name": att.file_name,
        "original_name": att.original_name,
        "mime_type": att.mime_type,
        "file_size_bytes": att.file_size_bytes,
        "storage_backend": att.storage_backend,
        "entity_type": att.entity_type,
        "entity_id": att.entity_id,
        "ai_tags": att.ai_tags_json,
        "ai_summary": att.ai_summary,
        "is_processed": att.is_processed,
        "created_at": att.created_at.isoformat() if att.created_at else None,
    }


@router.post("/upload", response_model=dict, status_code=201)
async def upload_media(
    file: UploadFile,
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    try:
        att = await media_storage.upload_file(
            db, org_id=int(user["org_id"]), file=file,
            user_id=int(user["id"]),
            entity_type=entity_type, entity_id=entity_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await record_action(
        db,
        event_type="media_uploaded",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="media_attachment",
        entity_id=att.id,
        payload_json={"original_name": att.original_name, "mime_type": att.mime_type, "size": att.file_size_bytes},
    )
    return _attachment_to_dict(att)


@router.post("/upload/bulk", response_model=list[dict], status_code=201)
async def upload_media_bulk(
    files: list[UploadFile],
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[dict]:
    results: list[dict] = []
    for file in files[:20]:  # Max 20 files per bulk upload
        try:
            att = await media_storage.upload_file(
                db, org_id=int(user["org_id"]), file=file,
                user_id=int(user["id"]),
                entity_type=entity_type, entity_id=entity_id,
            )
            results.append(_attachment_to_dict(att))
        except ValueError as e:
            results.append({"error": str(e), "file": file.filename})
    return results


@router.get("", response_model=list[dict])
async def list_media(
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    mime_prefix: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    atts = await media_storage.list_attachments(
        db, org_id=int(user["org_id"]),
        entity_type=entity_type, entity_id=entity_id,
        mime_prefix=mime_prefix, skip=skip, limit=limit,
    )
    return [_attachment_to_dict(a) for a in atts]


@router.get("/search", response_model=list[dict])
async def search_media_endpoint(
    q: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    results = await media_storage.search_media(
        db, org_id=int(user["org_id"]), query=q, skip=skip, limit=limit,
    )
    return [_attachment_to_dict(a) for a in results]


@router.get("/stats", response_model=dict)
async def media_stats(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await media_storage.get_storage_stats(db, org_id=int(user["org_id"]))


@router.get("/report", response_model=dict)
async def media_report(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await media_agent.generate_media_report(db, org_id=int(user["org_id"]))


@router.get("/{attachment_id}", response_model=dict)
async def get_media(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    att = await media_storage.get_attachment(db, attachment_id, org_id=int(user["org_id"]))
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return _attachment_to_dict(att)


@router.get("/{attachment_id}/download")
async def download_media(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> FileResponse:
    att = await media_storage.get_attachment(db, attachment_id, org_id=int(user["org_id"]))
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_path = media_storage.get_file_path(att)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        path=str(file_path),
        filename=att.original_name,
        media_type=att.mime_type,
    )


@router.post("/{attachment_id}/analyze", response_model=dict)
async def analyze_media(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    result = await media_agent.process_media(db, attachment_id, org_id=int(user["org_id"]))
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "Processing failed"))
    await record_action(
        db,
        event_type="media_analyzed",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="media_attachment",
        entity_id=attachment_id,
        payload_json={"tags": result.get("tags", [])},
    )
    return result


@router.post("/{attachment_id}/organize", response_model=dict)
async def organize_media(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await media_agent.auto_organize(db, attachment_id, org_id=int(user["org_id"]))


@router.patch("/{attachment_id}", response_model=dict)
async def update_media(
    attachment_id: int,
    entity_type: str | None = Query(None),
    entity_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    att = await media_storage.update_attachment(
        db, attachment_id, org_id=int(user["org_id"]),
        entity_type=entity_type, entity_id=entity_id,
    )
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return _attachment_to_dict(att)


@router.delete("/{attachment_id}", response_model=dict)
async def delete_media(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    att = await media_storage.soft_delete(db, attachment_id, org_id=int(user["org_id"]))
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await record_action(
        db,
        event_type="media_deleted",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="media_attachment",
        entity_id=attachment_id,
        payload_json={"original_name": att.original_name},
    )
    return {"id": att.id, "deleted": True}
