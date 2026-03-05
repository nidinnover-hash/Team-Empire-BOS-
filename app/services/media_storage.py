"""Media storage service — file persistence with local + S3-ready backends.

Handles upload, download, deletion, listing of media attachments.
AI processing is delegated to media_agent.py.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media_attachment import MediaAttachment

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# Pluggable scan hook — set to a callable(path: Path, mime: str) -> str | None.
# Return None to allow the upload, or a rejection reason string to block it.
_upload_scan_hook: Callable[[Path, str], str | None] | None = None


def set_upload_scan_hook(hook: Callable[[Path, str], str | None] | None) -> None:
    """Register (or clear) a scan hook that runs on every upload before DB insert."""
    global _upload_scan_hook
    _upload_scan_hook = hook

ALLOWED_MIME_PREFIXES = (
    "image/", "video/", "audio/",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "text/csv",
    "text/plain",
)


def _validate_mime(mime_type: str) -> bool:
    return any(mime_type.startswith(p) for p in ALLOWED_MIME_PREFIXES)


async def upload_file(
    db: AsyncSession,
    org_id: int,
    file: UploadFile,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> MediaAttachment:
    """Save uploaded file to disk and create DB record."""
    mime = file.content_type or "application/octet-stream"
    if not _validate_mime(mime):
        raise ValueError(f"File type not allowed: {mime}")

    now = datetime.now(UTC)
    raw_name = os.path.basename(file.filename or "upload")
    # Strip unsafe characters — keep only alphanumeric, dot, hyphen, underscore
    safe_name = "".join(c for c in raw_name if c.isalnum() or c in ".-_")[:200] or "upload"
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    rel_path = f"{org_id}/{now.year}/{now.month:02d}/{unique_name}"
    abs_path = Path(UPLOAD_DIR) / rel_path

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = 0
    chunk_size = 1024 * 1024
    try:
        with abs_path.open("wb") as f:
            while True:
                try:
                    chunk = await file.read(chunk_size)
                except TypeError:
                    # Compatibility with test doubles that don't accept size argument.
                    chunk = await file.read()
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    raise ValueError(f"File too large: {bytes_written} bytes (max {MAX_UPLOAD_MB}MB)")
                f.write(chunk)
    except Exception:
        abs_path.unlink(missing_ok=True)
        raise

    if _upload_scan_hook is not None:
        rejection = _upload_scan_hook(abs_path, mime)
        if rejection:
            abs_path.unlink(missing_ok=True)
            raise ValueError(f"Upload rejected by scan hook: {rejection}")

    attachment = MediaAttachment(
        organization_id=org_id,
        uploaded_by=user_id,
        file_name=unique_name,
        original_name=file.filename or "upload",
        mime_type=mime,
        file_size_bytes=bytes_written,
        storage_backend="local",
        storage_path=rel_path,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    logger.info("Uploaded media %s (%s, %d bytes)", attachment.id, mime, bytes_written)
    return attachment


async def get_attachment(
    db: AsyncSession,
    attachment_id: int,
    org_id: int,
) -> MediaAttachment | None:
    result = await db.execute(
        select(MediaAttachment).where(
            MediaAttachment.id == attachment_id,
            MediaAttachment.organization_id == org_id,
            MediaAttachment.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


def get_file_path(attachment: MediaAttachment) -> Path:
    """Return absolute file path for a local-stored attachment."""
    return Path(UPLOAD_DIR) / attachment.storage_path


async def list_attachments(
    db: AsyncSession,
    org_id: int,
    entity_type: str | None = None,
    entity_id: int | None = None,
    mime_prefix: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[MediaAttachment]:
    query = select(MediaAttachment).where(
        MediaAttachment.organization_id == org_id,
        MediaAttachment.is_deleted == False,  # noqa: E712
    )
    if entity_type:
        query = query.where(MediaAttachment.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(MediaAttachment.entity_id == entity_id)
    if mime_prefix:
        query = query.where(MediaAttachment.mime_type.startswith(mime_prefix))
    query = query.order_by(MediaAttachment.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_attachment(
    db: AsyncSession,
    attachment_id: int,
    org_id: int,
    entity_type: str | None = None,
    entity_id: int | None = None,
    ai_tags_json: dict | None = None,
    ai_summary: str | None = None,
    is_processed: bool | None = None,
) -> MediaAttachment | None:
    att = await get_attachment(db, attachment_id, org_id)
    if att is None:
        return None
    if entity_type is not None:
        att.entity_type = entity_type
    if entity_id is not None:
        att.entity_id = entity_id
    if ai_tags_json is not None:
        att.ai_tags_json = ai_tags_json
    if ai_summary is not None:
        att.ai_summary = ai_summary
    if is_processed is not None:
        att.is_processed = is_processed
    att.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(att)
    return att


async def soft_delete(
    db: AsyncSession,
    attachment_id: int,
    org_id: int,
) -> MediaAttachment | None:
    att = await get_attachment(db, attachment_id, org_id)
    if att is None:
        return None
    att.is_deleted = True
    att.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(att)
    return att


async def search_media(
    db: AsyncSession,
    org_id: int,
    query: str,
    skip: int = 0,
    limit: int = 20,
) -> list[MediaAttachment]:
    """Simple text search across AI summary and tags."""
    pattern = f"%{query}%"
    stmt = (
        select(MediaAttachment)
        .where(
            MediaAttachment.organization_id == org_id,
            MediaAttachment.is_deleted == False,  # noqa: E712
            MediaAttachment.is_processed == True,  # noqa: E712
            (
                MediaAttachment.ai_summary.ilike(pattern)
                | MediaAttachment.original_name.ilike(pattern)
            ),
        )
        .order_by(MediaAttachment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_storage_stats(
    db: AsyncSession,
    org_id: int,
) -> dict:
    """Storage usage stats for an organization."""
    total_count = int(
        (await db.execute(
            select(func.count(MediaAttachment.id)).where(
                MediaAttachment.organization_id == org_id,
                MediaAttachment.is_deleted == False,  # noqa: E712
            )
        )).scalar_one() or 0
    )
    total_bytes = int(
        (await db.execute(
            select(func.sum(MediaAttachment.file_size_bytes)).where(
                MediaAttachment.organization_id == org_id,
                MediaAttachment.is_deleted == False,  # noqa: E712
            )
        )).scalar_one() or 0
    )
    processed_count = int(
        (await db.execute(
            select(func.count(MediaAttachment.id)).where(
                MediaAttachment.organization_id == org_id,
                MediaAttachment.is_deleted == False,  # noqa: E712
                MediaAttachment.is_processed == True,  # noqa: E712
            )
        )).scalar_one() or 0
    )
    return {
        "total_files": total_count,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "processed_count": processed_count,
        "unprocessed_count": total_count - processed_count,
    }
