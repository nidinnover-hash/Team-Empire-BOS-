"""AI-powered media processing agent.

Analyzes uploaded files to auto-generate descriptions, tags, and summaries.
Uses call_ai() for LLM-powered analysis with graceful fallback.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import media_storage

logger = logging.getLogger(__name__)


async def _call_ai_safe(system_prompt: str, user_message: str) -> str:
    """Call AI with graceful fallback."""
    try:
        from app.services.ai_router import call_ai
        return await call_ai(
            system_prompt=system_prompt,
            user_message=user_message,
            provider="openai",
            max_tokens=800,
        )
    except Exception as exc:
        logger.warning("Media AI call failed: %s", exc)
        return json.dumps({
            "tags": ["unprocessed"],
            "description": "AI analysis unavailable.",
            "_fallback": True,
        })


async def process_media(
    db: AsyncSession,
    attachment_id: int,
    org_id: int,
) -> dict:
    """Run AI analysis on a media attachment."""
    att = await media_storage.get_attachment(db, attachment_id, org_id)
    if att is None:
        return {"ok": False, "error": "Attachment not found"}

    mime = att.mime_type or ""
    file_path = media_storage.get_file_path(att)

    system_prompt = (
        "You are an AI media analyst for a business operating system. "
        "Analyze the described file and return JSON with keys: "
        "tags (list of keyword strings), description (1-2 sentence summary), "
        "category (one of: document, photo, screenshot, presentation, spreadsheet, video, audio, other)."
    )

    # Build context based on file type
    if mime.startswith("image/"):
        user_msg = (
            f"Image file: {att.original_name}\n"
            f"MIME type: {mime}\n"
            f"File size: {att.file_size_bytes} bytes\n"
            "Describe what this image likely contains based on the filename and context."
        )
    elif mime.startswith("video/"):
        user_msg = (
            f"Video file: {att.original_name}\n"
            f"MIME type: {mime}\n"
            f"File size: {att.file_size_bytes} bytes\n"
            "Describe what this video likely contains based on the filename."
        )
    elif mime == "application/pdf" or mime.startswith("application/vnd"):
        # For documents, try to read first few KB of text
        text_preview = ""
        if file_path.exists() and att.file_size_bytes < 500_000:
            try:
                raw = file_path.read_bytes()[:2000]
                text_preview = raw.decode("utf-8", errors="ignore")[:500]
            except OSError as exc:
                logger.debug("Document preview read failed for attachment=%s: %s", att.id, type(exc).__name__)
        user_msg = (
            f"Document file: {att.original_name}\n"
            f"MIME type: {mime}\n"
            f"File size: {att.file_size_bytes} bytes\n"
            f"Text preview: {text_preview[:300] if text_preview else 'Binary content'}\n"
            "Summarize the document and generate tags."
        )
    else:
        user_msg = (
            f"File: {att.original_name}\n"
            f"MIME type: {mime}\n"
            f"File size: {att.file_size_bytes} bytes\n"
            "Describe this file and generate relevant tags."
        )

    ai_response = await _call_ai_safe(system_prompt, user_msg)

    try:
        parsed = json.loads(ai_response)
    except (json.JSONDecodeError, TypeError):
        parsed = {"tags": ["unprocessed"], "description": ai_response[:500]}

    tags = parsed.get("tags", [])
    description = parsed.get("description", "")
    category = parsed.get("category", "other")

    ai_tags = {
        "tags": tags,
        "category": category,
        "mime_type": mime,
        "original_name": att.original_name,
    }

    await media_storage.update_attachment(
        db, attachment_id, org_id,
        ai_tags_json=ai_tags,
        ai_summary=description,
        is_processed=True,
    )

    return {
        "ok": True,
        "attachment_id": attachment_id,
        "tags": tags,
        "description": description,
        "category": category,
    }


async def auto_organize(
    db: AsyncSession,
    attachment_id: int,
    org_id: int,
) -> dict:
    """AI suggests entity linkage based on content analysis."""
    att = await media_storage.get_attachment(db, attachment_id, org_id)
    if att is None:
        return {"ok": False, "error": "Attachment not found"}

    summary = att.ai_summary or att.original_name
    tags = att.ai_tags_json or {}

    system_prompt = (
        "You are an AI file organizer. Based on the file description and tags, "
        "suggest which entity type this file belongs to. "
        "Return JSON with: entity_type (employee/project/task/note/general), "
        "reason (why this linkage makes sense)."
    )
    user_msg = f"File: {att.original_name}\nSummary: {summary}\nTags: {json.dumps(tags)}"

    ai_response = await _call_ai_safe(system_prompt, user_msg)

    try:
        parsed = json.loads(ai_response)
    except (json.JSONDecodeError, TypeError):
        parsed = {"entity_type": "general", "reason": "Could not determine"}

    return {
        "ok": True,
        "attachment_id": attachment_id,
        "suggested_entity_type": parsed.get("entity_type", "general"),
        "reason": parsed.get("reason", ""),
    }


async def generate_media_report(
    db: AsyncSession,
    org_id: int,
) -> dict:
    """Generate storage usage and analytics report."""
    stats = await media_storage.get_storage_stats(db, org_id)

    # Get file type breakdown
    all_files = await media_storage.list_attachments(db, org_id, limit=1000)
    type_counts: dict[str, int] = {}
    for f in all_files:
        category = "other"
        if f.ai_tags_json and isinstance(f.ai_tags_json, dict):
            category = f.ai_tags_json.get("category", "other")
        elif f.mime_type:
            if f.mime_type.startswith("image/"):
                category = "image"
            elif f.mime_type.startswith("video/"):
                category = "video"
            elif f.mime_type.startswith("audio/"):
                category = "audio"
            elif "pdf" in f.mime_type or "document" in f.mime_type:
                category = "document"
        type_counts[category] = type_counts.get(category, 0) + 1

    unlinked = sum(1 for f in all_files if not f.entity_type)

    return {
        **stats,
        "type_breakdown": type_counts,
        "unlinked_files": unlinked,
    }
