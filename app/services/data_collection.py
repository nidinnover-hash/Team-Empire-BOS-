from __future__ import annotations

from datetime import date
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_collection import (
    CloneProTrainingRequest,
    CloneProTrainingResult,
    DataCollectRequest,
    DataCollectResult,
)
from app.schemas.memory import DailyContextCreate
from app.schemas.note import NoteCreate
from app.services import memory as memory_service
from app.services import note as note_service

_MAX_ITEMS = 25
_MAX_ITEM_CHARS = 300
_ALLOWED_CONTEXT_TYPES = {"priority", "meeting", "blocker", "decision"}
_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,100}$")
_MAX_PRO_ITEM_CHARS = 220


def _normalize_items(content: str, split_lines: bool) -> list[str]:
    text = (content or "").strip()
    if not text:
        return []
    if not split_lines:
        return [text[:_MAX_ITEM_CHARS]]
    raw = text.splitlines()
    items = [line.strip(" -*\t\r")[:_MAX_ITEM_CHARS] for line in raw if line.strip()]
    return items[:_MAX_ITEMS]


def _normalize_pro_items(items: list[str], limit: int) -> list[str]:
    cleaned: list[str] = []
    for raw in items:
        text = (raw or "").strip(" -*\t\r")
        if not text:
            continue
        cleaned.append(text[:_MAX_PRO_ITEM_CHARS])
        if len(cleaned) >= limit:
            break
    return cleaned


async def ingest_data(
    db: AsyncSession,
    org_id: int,
    data: DataCollectRequest,
) -> DataCollectResult:
    items = _normalize_items(data.content, data.split_lines)
    if not items:
        return DataCollectResult(
            target=data.target,
            source=data.source,
            ingested_count=0,
            created_ids=[],
            message="No non-empty content to ingest.",
        )

    created_ids: list[int] = []
    if data.target == "profile_memory":
        key = (data.key or "").strip()
        if not key:
            raise ValueError("key is required when target=profile_memory")
        if not _KEY_PATTERN.match(key):
            raise ValueError("key must match [a-zA-Z0-9_.-] and be 3-100 chars")
        category = data.category or "ingested"
        if data.split_lines and len(items) > 1:
            for idx, item in enumerate(items, start=1):
                entry = await memory_service.upsert_profile_memory(
                    db=db,
                    organization_id=org_id,
                    key=f"{key}.{idx}",
                    value=item,
                    category=category,
                )
                created_ids.append(entry.id)
        else:
            entry = await memory_service.upsert_profile_memory(
                db=db,
                organization_id=org_id,
                key=key,
                value=items[0],
                category=category,
            )
            created_ids.append(entry.id)

    elif data.target == "daily_context":
        ctx_type = (data.context_type or "priority").strip().lower() or "priority"
        if ctx_type not in _ALLOWED_CONTEXT_TYPES:
            raise ValueError("context_type must be one of: priority, meeting, blocker, decision")
        ctx_date = data.for_date or date.today()
        for item in items:
            entry = await memory_service.add_daily_context(
                db=db,
                organization_id=org_id,
                data=DailyContextCreate(
                    date=ctx_date,
                    context_type=ctx_type,
                    content=item,
                    related_to=data.related_to,
                ),
            )
            created_ids.append(entry.id)

    else:  # notes
        tags = f"ingested,{data.source}".strip(",")
        for item in items:
            note = await note_service.create_note(
                db=db,
                organization_id=org_id,
                data=NoteCreate(
                    title=f"Ingested from {data.source}",
                    content=item,
                    tags=tags,
                ),
            )
            created_ids.append(note.id)

    return DataCollectResult(
        target=data.target,
        source=data.source,
        ingested_count=len(created_ids),
        created_ids=created_ids,
        message=f"Ingested {len(created_ids)} item(s) into {data.target}.",
    )


async def train_clone_pro(
    db: AsyncSession,
    org_id: int,
    data: CloneProTrainingRequest,
) -> CloneProTrainingResult:
    memory_keys: list[str] = []
    profile_memory_written = 0
    daily_context_written = 0
    notes_written = 0

    priorities = _normalize_pro_items(data.top_priorities, limit=10)
    if not priorities:
        raise ValueError("top_priorities must include at least one non-empty value")

    operating_rules = _normalize_pro_items(data.operating_rules, limit=10)
    daily_focus = _normalize_pro_items(data.daily_focus, limit=8)
    domain_notes = _normalize_pro_items(data.domain_notes, limit=12)

    if data.preferred_name and data.preferred_name.strip():
        key = "identity.preferred_name"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key,
            value=data.preferred_name.strip()[:80],
            category="learned",
        )
        profile_memory_written += 1
        memory_keys.append(key)

    key = "preference.communication_style"
    await memory_service.upsert_profile_memory(
        db=db,
        organization_id=org_id,
        key=key,
        value=data.communication_style.strip()[:_MAX_PRO_ITEM_CHARS],
        category="learned",
    )
    profile_memory_written += 1
    memory_keys.append(key)

    for idx, priority in enumerate(priorities, start=1):
        p_key = f"work.priority.{idx}"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=p_key,
            value=priority,
            category="learned",
        )
        profile_memory_written += 1
        memory_keys.append(p_key)

    if priorities:
        key = "work.priority_focus"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key,
            value=priorities[0],
            category="learned",
        )
        profile_memory_written += 1
        memory_keys.append(key)

    for idx, rule in enumerate(operating_rules, start=1):
        key = f"work.operating_rule.{idx}"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key,
            value=rule,
            category="learned",
        )
        profile_memory_written += 1
        memory_keys.append(key)

    for item in daily_focus:
        await memory_service.add_daily_context(
            db=db,
            organization_id=org_id,
            data=DailyContextCreate(
                date=date.today(),
                context_type="priority",
                content=item,
                related_to="pro_training",
            ),
        )
        daily_context_written += 1

    for idx, note_text in enumerate(domain_notes, start=1):
        await note_service.create_note(
            db=db,
            organization_id=org_id,
            data=NoteCreate(
                title=f"Pro Training Note {idx}",
                content=note_text,
                tags="training,pro_clone,knowledge",
            ),
        )
        notes_written += 1

    return CloneProTrainingResult(
        source=data.source,
        profile_memory_written=profile_memory_written,
        daily_context_written=daily_context_written,
        notes_written=notes_written,
        memory_keys=memory_keys,
        message=(
            "Pro clone training completed: profile memory updated, "
            "daily focus queued, and domain notes stored."
        ),
    )
