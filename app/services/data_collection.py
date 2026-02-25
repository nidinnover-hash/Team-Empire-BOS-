from __future__ import annotations

from datetime import date
import re
from collections import Counter
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_rule import PolicyRule
from app.schemas.data_collection import (
    CloneProTrainingRequest,
    CloneProTrainingResult,
    MobileCaptureAnalyzeRequest,
    MobileCaptureAnalyzeResult,
    MeetingCoachingRequest,
    MeetingCoachingResult,
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
_FILLER_WORDS = {"um", "uh", "like", "basically", "actually", "just", "you know"}
_EMPATHY_WORDS = {"understand", "appreciate", "help", "support", "value", "thanks"}
_CLOSE_WORDS = {"next step", "timeline", "proposal", "confirm", "decision", "start"}
_OBJECTION_WORDS = {"concern", "problem", "expensive", "budget", "not sure", "later"}
_WANTED_HINTS = {
    "meeting", "task", "deadline", "follow up", "roadmap", "project", "client", "sales",
    "invoice", "approval", "learning", "study", "review", "priority", "plan", "kpi",
}
_UNWANTED_HINTS = {
    "gambling", "bet", "porn", "explicit", "nude", "phishing", "scam", "torrent", "piracy",
    "crack", "hate", "violence", "abuse", "fraud", "spam", "deepfake",
}


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


def _coaching_sentences(transcript: str) -> list[str]:
    clean = re.sub(r"\s+", " ", transcript or "").strip()
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+", clean)
    return [p.strip() for p in parts if p.strip()]


async def analyze_meeting_transcript(
    db: AsyncSession,
    org_id: int,
    data: MeetingCoachingRequest,
) -> MeetingCoachingResult:
    if not data.consent_confirmed:
        raise ValueError("consent_confirmed must be true before processing real conversations")

    text = (data.transcript or "").strip()
    if not text:
        raise ValueError("transcript is required")

    lowered = text.lower()
    words = re.findall(r"[a-zA-Z']+", lowered)
    word_count = len(words)
    question_count = text.count("?")
    filler_count = sum(1 for w in words if w in _FILLER_WORDS)
    empathy_count = sum(1 for w in words if w in _EMPATHY_WORDS)
    close_hits = sum(lowered.count(token) for token in _CLOSE_WORDS)
    objection_hits = sum(lowered.count(token) for token in _OBJECTION_WORDS)
    sentence_count = max(1, len(_coaching_sentences(text)))
    avg_sentence_words = round(word_count / sentence_count, 1)

    strengths: list[str] = []
    improvements: list[str] = []
    if question_count >= 4:
        strengths.append("Strong discovery questioning pattern.")
    else:
        improvements.append("Ask more discovery questions to understand customer needs earlier.")
    if empathy_count >= 2:
        strengths.append("Good empathy language and support framing.")
    else:
        improvements.append("Add empathy phrases before pitching solutions.")
    if close_hits >= 2:
        strengths.append("Conversation includes clear next-step or closing intent.")
    else:
        improvements.append("End with one clear next step and decision checkpoint.")
    if avg_sentence_words <= 22:
        strengths.append("Messaging is concise and easy to follow.")
    else:
        improvements.append("Reduce sentence length for clearer delivery in live calls.")
    if filler_count > 8:
        improvements.append("Reduce filler words for stronger executive presence.")

    tone_profile = "consultative"
    if empathy_count <= 1 and question_count <= 2:
        tone_profile = "pitch-heavy"
    elif empathy_count >= 3 and question_count >= 4:
        tone_profile = "advisor-led"

    common_terms = Counter([w for w in words if len(w) >= 5]).most_common(3)
    top_term_str = ", ".join(t for t, _ in common_terms) if common_terms else "none"

    memory_keys: list[str] = []
    for key, value in [
        ("sales.talk.tone_profile", tone_profile),
        ("sales.talk.discovery_questions", str(question_count)),
        ("sales.talk.next_step_focus", str(close_hits)),
    ]:
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key,
            value=value[:_MAX_PRO_ITEM_CHARS],
            category="learned",
        )
        memory_keys.append(key)

    coach_note = await note_service.create_note(
        db=db,
        organization_id=org_id,
        data=NoteCreate(
            title=f"Meeting Coaching - {(data.speaker_name or 'Speaker').strip()[:60]}",
            content=(
                f"Objective: {data.objective}\n"
                f"Tone Profile: {tone_profile}\n"
                f"Word Count: {word_count}\n"
                f"Questions: {question_count}\n"
                f"Filler Words: {filler_count}\n"
                f"Top Terms: {top_term_str}\n"
                f"Strengths: {' | '.join(strengths[:4]) or 'n/a'}\n"
                f"Improvements: {' | '.join(improvements[:5]) or 'n/a'}"
            ),
            tags="meeting,conversation,coaching,sales",
        ),
    )

    return MeetingCoachingResult(
        objective=data.objective,
        tone_profile=tone_profile,
        strengths=strengths[:5],
        improvement_areas=improvements[:6],
        sales_signals={
            "question_count": question_count,
            "empathy_count": empathy_count,
            "close_signal_count": close_hits,
            "objection_signal_count": objection_hits,
            "filler_count": filler_count,
        },
        memory_keys=memory_keys,
        note_id=coach_note.id,
        message=(
            "Conversation coaching generated. Transcript converted into clone-ready "
            "talk and sales improvement signals."
        ),
    )


def _mobile_lines(content_text: str) -> list[str]:
    raw = [line.strip(" -*\t\r") for line in (content_text or "").splitlines()]
    lines = [x for x in raw if x]
    if len(lines) <= 1:
        # Fallback for paragraph-only OCR text.
        return [s.strip() for s in re.split(r"[.!?]\s+", content_text) if s.strip()][:120]
    return lines[:180]


def _score_line(line: str, wanted_topics: list[str], unwanted_topics: list[str]) -> tuple[str, str]:
    text = line.lower()
    wanted_hits = sum(1 for token in _WANTED_HINTS if token in text)
    unwanted_hits = sum(1 for token in _UNWANTED_HINTS if token in text)
    wanted_hits += sum(2 for token in wanted_topics if token and token.lower() in text)
    unwanted_hits += sum(2 for token in unwanted_topics if token and token.lower() in text)
    if unwanted_hits > wanted_hits and unwanted_hits > 0:
        reason = "matched unwanted patterns"
        return "unwanted", reason
    if wanted_hits > 0:
        reason = "matched wanted/work patterns"
        return "wanted", reason
    return "neutral", "no strong signal"


async def analyze_mobile_capture(
    db: AsyncSession,
    org_id: int,
    data: MobileCaptureAnalyzeRequest,
) -> MobileCaptureAnalyzeResult:
    lines = _mobile_lines(data.content_text)
    if not lines:
        raise ValueError("content_text did not produce any analyzable lines")

    wanted_lines: list[str] = []
    unwanted_lines: list[str] = []
    for line in lines:
        label, _reason = _score_line(line, data.wanted_topics, data.unwanted_topics)
        if label == "wanted":
            wanted_lines.append(line[:_MAX_ITEM_CHARS])
        elif label == "unwanted":
            unwanted_lines.append(line[:_MAX_ITEM_CHARS])

    memory_keys: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for idx, text in enumerate(wanted_lines[:30], start=1):
        key = f"mobile.capture.{data.device_type}.{stamp}.{idx}"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key,
            value=text,
            category="learned",
        )
        memory_keys.append(key)

    # Feed actionable wanted items into daily context for operational recall.
    for text in wanted_lines[:8]:
        await memory_service.add_daily_context(
            db=db,
            organization_id=org_id,
            data=DailyContextCreate(
                date=date.today(),
                context_type="priority",
                content=text,
                related_to="mobile_capture",
            ),
        )

    policy_rule_ids: list[int] = []
    if data.create_policy_drafts and unwanted_lines:
        grouped: dict[str, list[str]] = {}
        for text in unwanted_lines[:40]:
            topic = "unsafe_content"
            for token in sorted(_UNWANTED_HINTS, key=len, reverse=True):
                if token in text.lower():
                    topic = token
                    break
            grouped.setdefault(topic, []).append(text)

        for topic, examples in list(grouped.items())[:8]:
            policy = PolicyRule(
                organization_id=org_id,
                title=f"Mobile Capture Guardrail: {topic}",
                rule_text=(
                    f"Block or quarantine captured knowledge related to '{topic}' "
                    "from mobile/tablet screenshots unless manually approved."
                ),
                examples_json=json.dumps(examples[:6]),
                is_active=False,
            )
            db.add(policy)
            await db.flush()
            policy_rule_ids.append(int(policy.id))

    note = await note_service.create_note(
        db=db,
        organization_id=org_id,
        data=NoteCreate(
            title=f"Mobile Capture Analysis ({data.device_type}/{data.capture_type})",
            content=(
                f"Scanned lines: {len(lines)}\n"
                f"Wanted signals: {len(wanted_lines)}\n"
                f"Unwanted signals: {len(unwanted_lines)}\n"
                f"Policy drafts: {len(policy_rule_ids)}"
            ),
            tags="mobile_capture,analysis,policy",
        ),
    )
    await db.commit()

    return MobileCaptureAnalyzeResult(
        source=data.source,
        device_type=data.device_type,
        capture_type=data.capture_type,
        scanned_lines=len(lines),
        wanted_count=len(wanted_lines),
        unwanted_count=len(unwanted_lines),
        memory_keys=memory_keys,
        policy_rule_ids=policy_rule_ids,
        note_id=note.id,
        message=(
            "Mobile capture analyzed. Wanted knowledge fed into memory/context; "
            "unwanted knowledge converted into policy drafts."
        ),
    )


def parse_topic_tokens(raw: str | None) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()][:20]
        except Exception:
            pass
    tokens = re.split(r"[,;\n]", text)
    return [tok.strip() for tok in tokens if tok.strip()][:20]


def extract_text_from_image_bytes(image_bytes: bytes) -> tuple[str, str]:
    if not image_bytes:
        raise ValueError("empty image payload")
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - dependency availability
        raise RuntimeError(
            "Pillow is required for image OCR. Install with: pip install pillow"
        ) from exc
    try:
        import pytesseract  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - dependency availability
        raise RuntimeError(
            "pytesseract is required for OCR. Install with: pip install pytesseract "
            "and ensure Tesseract OCR binary is installed on the host."
        ) from exc

    # Windows safety net: use common install path if PATH isn't refreshed.
    current_cmd = str(getattr(pytesseract.pytesseract, "tesseract_cmd", "") or "").strip()
    if not current_cmd or current_cmd.lower() == "tesseract" or not Path(current_cmd).exists():
        candidate = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)

    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError("invalid image payload") from exc

    text = (pytesseract.image_to_string(image) or "").strip()
    if not text:
        raise ValueError("no text detected in image")
    return text, "pytesseract"
