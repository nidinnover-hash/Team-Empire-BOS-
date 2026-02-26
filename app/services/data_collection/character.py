from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_collection import PhotoCharacterStudyResult
from app.schemas.note import NoteCreate
from app.services import memory as memory_service
from app.services import note as note_service

# ── Photo Character Study ──────────────────────────────────────────────────────

_CHARACTER_TRAIT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "analytical": ("data", "metrics", "analysis", "report", "dashboard", "kpi", "measure"),
    "decisive": ("decision", "decide", "confirm", "approve", "execute", "action", "done"),
    "empathetic": ("understand", "feel", "support", "help", "care", "concern", "listen"),
    "strategic": ("strategy", "plan", "roadmap", "vision", "growth", "scale", "long-term"),
    "detail-oriented": ("detail", "checklist", "review", "audit", "verify", "spec", "exact"),
    "collaborative": ("team", "together", "align", "sync", "meeting", "group", "shared"),
    "creative": ("idea", "design", "brainstorm", "innovate", "concept", "creative", "new"),
    "results-driven": ("result", "outcome", "target", "goal", "achieve", "deliver", "deadline"),
    "communicative": ("update", "notify", "inform", "share", "present", "communicate", "call"),
    "organized": ("organize", "schedule", "calendar", "priority", "task", "list", "order"),
}


def _extract_character_traits(text: str) -> list[str]:
    lowered = text.lower()
    scored: list[tuple[str, int]] = []
    for trait, keywords in _CHARACTER_TRAIT_KEYWORDS.items():
        hits = sum(lowered.count(kw) for kw in keywords)
        if hits > 0:
            scored.append((trait, hits))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scored[:6]]


def _character_confidence(traits: list[str], text_len: int) -> str:
    if len(traits) >= 4 and text_len >= 200:
        return "high"
    if len(traits) >= 2 and text_len >= 80:
        return "medium"
    return "low"


async def analyze_photo_character(
    db: AsyncSession,
    org_id: int,
    extracted_text: str,
    ocr_engine: str,
    filename: str,
) -> PhotoCharacterStudyResult:
    text = (extracted_text or "").strip()
    if not text:
        raise ValueError("no text content to analyze")

    traits = _extract_character_traits(text)
    confidence = _character_confidence(traits, len(text))

    if traits:
        summary = (
            f"Character profile based on captured content: "
            f"Dominant traits are {', '.join(traits[:3])}. "
            f"Analysis confidence: {confidence}."
        )
    else:
        summary = "Insufficient content signals for character trait extraction."
        traits = ["undetermined"]

    memory_keys: list[str] = []
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    for trait in traits:
        key = f"character.trait.{trait.replace('-', '_')}.{stamp}"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key[:100],
            value=f"Detected trait: {trait} (confidence: {confidence})",
            category="character_study",
        )
        memory_keys.append(key[:100])

    if len(traits) >= 2:
        style_key = f"character.study.summary.{stamp}"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=style_key[:100],
            value=summary[:220],
            category="character_study",
        )
        memory_keys.append(style_key[:100])

    note = await note_service.create_note(
        db=db,
        organization_id=org_id,
        data=NoteCreate(
            title=f"Character Study - {filename[:60]}",
            content=(
                f"File: {filename}\n"
                f"OCR Engine: {ocr_engine}\n"
                f"Extracted Chars: {len(text)}\n"
                f"Traits: {', '.join(traits)}\n"
                f"Confidence: {confidence}\n"
                f"Summary: {summary}"
            ),
            tags="character_study,photo,training",
        ),
    )
    await db.commit()

    return PhotoCharacterStudyResult(
        filename=filename,
        extracted_chars=len(text),
        ocr_engine=ocr_engine,
        traits=traits,
        character_summary=summary,
        confidence=confidence,
        memory_keys=memory_keys,
        note_id=note.id,
        message="Photo character study completed. Traits fed into brain memory layer.",
    )
