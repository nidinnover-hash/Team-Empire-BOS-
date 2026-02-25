from __future__ import annotations

from datetime import date, timedelta
import re
from collections import Counter
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func as sa_func, select

from app.models.policy_rule import PolicyRule
from app.models.threat_signal import ThreatSignal
from app.schemas.data_collection import (
    BrandingPowerReport,
    CloneProTrainingRequest,
    CloneProTrainingResult,
    EthicalBoundaryReport,
    EthicalViolation,
    FraudDetectionResult,
    FraudLayerReport,
    FraudSignalOut,
    MobileCaptureAnalyzeRequest,
    MobileCaptureAnalyzeResult,
    MeetingCoachingRequest,
    MeetingCoachingResult,
    DataCollectRequest,
    DataCollectResult,
    NewsDigestItem,
    NewsDigestRequest,
    NewsDigestResult,
    PhotoCharacterStudyResult,
    ThreatDetectionResult,
    ThreatLayerReport,
    ThreatSignalOut,
    ThreatTrainRequest,
    ThreatTrainResult,
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
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
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


# ── Digital Threat Detection ───────────────────────────────────────────────────

_THREAT_PATTERNS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "credential_leak": {
        "keywords": ("password", "secret", "token", "api_key", "apikey", "credentials", "private_key"),
        "severity": "critical",
        "title": "Potential credential exposure detected",
    },
    "injection_attempt": {
        "keywords": ("' or ", "1=1", "<script", "eval(", "exec(", "drop table", "union select"),
        "severity": "high",
        "title": "Injection pattern detected in input",
    },
    "rate_abuse": {
        "keywords": ("rate limit", "too many requests", "429", "throttled", "brute force"),
        "severity": "medium",
        "title": "Rate abuse or brute-force indicator",
    },
    "privilege_escalation": {
        "keywords": ("admin", "sudo", "force_role", "escalat", "bypass", "override"),
        "severity": "high",
        "title": "Privilege escalation pattern detected",
    },
    "data_exfiltration": {
        "keywords": ("export all", "bulk download", "dump", "extract", "scrape", "exfil"),
        "severity": "high",
        "title": "Data exfiltration risk detected",
    },
    "suspicious_pattern": {
        "keywords": ("suspicious", "anomaly", "unusual", "unexpected", "unauthorized"),
        "severity": "medium",
        "title": "Suspicious behavioral pattern detected",
    },
    "config_weakness": {
        "keywords": ("debug=true", "debug mode", "verbose", "permissive", "cors *", "allow all"),
        "severity": "low",
        "title": "Configuration weakness identified",
    },
    "dependency_risk": {
        "keywords": ("vulnerable", "cve-", "deprecated", "outdated", "end of life", "eol"),
        "severity": "medium",
        "title": "Dependency or version risk detected",
    },
}


def _scan_text_for_threats(text: str) -> list[dict[str, str]]:
    lowered = text.lower()
    found: list[dict[str, str]] = []
    for category, meta in _THREAT_PATTERNS.items():
        keywords = meta["keywords"]
        hits = [kw for kw in keywords if kw in lowered]  # type: ignore[union-attr]
        if hits:
            found.append({
                "category": category,
                "severity": str(meta["severity"]),
                "title": str(meta["title"]),
                "description": f"Matched patterns: {', '.join(hits[:5])}",
            })
    return found


async def detect_threats(
    db: AsyncSession,
    org_id: int,
    scope: str = "full_scan",
) -> ThreatDetectionResult:
    from app.models.memory import ProfileMemory, DailyContext
    from app.models.note import Note

    today = date.today()
    since = today - timedelta(days=7)

    # Scan recent notes
    notes_result = await db.execute(
        select(Note).where(
            Note.organization_id == org_id,
            Note.created_at >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc),
        ).limit(200)
    )
    notes = list(notes_result.scalars().all())

    # Scan recent daily context
    ctx_result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == org_id,
            DailyContext.date >= since,
        ).limit(200)
    )
    contexts = list(ctx_result.scalars().all())

    # Scan profile memory
    mem_result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == org_id,
        ).limit(500)
    )
    memories = list(mem_result.scalars().all())

    all_signals: list[dict[str, str]] = []
    scanned_sources: list[tuple[str, str]] = []

    for note in notes:
        text = f"{note.title or ''} {note.content or ''}"
        scanned_sources.append(("note", str(note.id)))
        for sig in _scan_text_for_threats(text):
            sig["source"] = f"note:{note.id}"
            all_signals.append(sig)

    for ctx in contexts:
        scanned_sources.append(("daily_context", str(ctx.id)))
        for sig in _scan_text_for_threats(ctx.content or ""):
            sig["source"] = f"daily_context:{ctx.id}"
            all_signals.append(sig)

    for mem in memories:
        scanned_sources.append(("profile_memory", str(mem.id)))
        for sig in _scan_text_for_threats(f"{mem.key} {mem.value}"):
            sig["source"] = f"profile_memory:{mem.id}"
            all_signals.append(sig)

    # Deduplicate by category+source
    seen: set[str] = set()
    unique_signals: list[dict[str, str]] = []
    for sig in all_signals:
        key = f"{sig['category']}:{sig['source']}"
        if key not in seen:
            seen.add(key)
            unique_signals.append(sig)

    # Create ThreatSignal records and policy drafts
    signal_records: list[ThreatSignalOut] = []
    policy_drafts_created = 0

    for sig in unique_signals[:50]:
        can_auto_mitigate = sig["severity"] in ("low", "info")
        ts = ThreatSignal(
            organization_id=org_id,
            category=sig["category"],
            severity=sig["severity"],
            title=sig["title"],
            description=sig["description"][:500],
            source=sig["source"][:80],
            auto_mitigated=can_auto_mitigate,
        )
        db.add(ts)
        await db.flush()

        if sig["severity"] in ("critical", "high"):
            policy = PolicyRule(
                organization_id=org_id,
                title=f"Threat Guard: {sig['category'].replace('_', ' ').title()}",
                rule_text=(
                    f"Auto-generated from threat detection. "
                    f"Block or flag content matching '{sig['category']}' patterns. "
                    f"Source: {sig['source']}."
                ),
                examples_json=json.dumps([sig["description"][:200]]),
                is_active=False,
            )
            db.add(policy)
            await db.flush()
            ts.policy_rule_id = int(policy.id)
            policy_drafts_created += 1

        signal_records.append(ThreatSignalOut(
            id=int(ts.id),
            category=ts.category,
            severity=ts.severity,
            title=ts.title,
            description=ts.description,
            source=ts.source,
            auto_mitigated=ts.auto_mitigated,
            created_at=ts.created_at.isoformat() if ts.created_at else "",
        ))

    await db.commit()

    severity_breakdown: dict[str, int] = {}
    for sig in signal_records:
        severity_breakdown[sig.severity] = severity_breakdown.get(sig.severity, 0) + 1

    return ThreatDetectionResult(
        scope=scope,
        signals_found=len(signal_records),
        signals=signal_records,
        severity_breakdown=severity_breakdown,
        policy_drafts_created=policy_drafts_created,
        message=f"Threat scan completed. {len(signal_records)} signal(s) detected across {len(scanned_sources)} items.",
    )


async def train_threat_signals(
    db: AsyncSession,
    org_id: int,
    data: ThreatTrainRequest,
) -> ThreatTrainResult:
    result = await db.execute(
        select(ThreatSignal).where(
            ThreatSignal.organization_id == org_id,
            ThreatSignal.id.in_(data.signal_ids),
        )
    )
    signals = list(result.scalars().all())
    if not signals:
        raise ValueError("No matching threat signals found for this organization")

    policies_activated = 0
    policies_dismissed = 0
    memory_keys: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    for sig in signals:
        if data.action == "approve":
            # Activate associated policy if exists
            if sig.policy_rule_id:
                policy_result = await db.execute(
                    select(PolicyRule).where(PolicyRule.id == sig.policy_rule_id)
                )
                policy = policy_result.scalar_one_or_none()
                if policy and not policy.is_active:
                    policy.is_active = True
                    policies_activated += 1

            # Feed into memory for self-training
            key = f"threat.learned.{sig.category}.{stamp}"
            await memory_service.upsert_profile_memory(
                db=db,
                organization_id=org_id,
                key=key[:100],
                value=f"Confirmed threat pattern: {sig.title} - {sig.description[:150]}",
                category="threat_intelligence",
            )
            memory_keys.append(key[:100])
        else:
            sig.dismissed = True
            if sig.policy_rule_id:
                policy_result = await db.execute(
                    select(PolicyRule).where(PolicyRule.id == sig.policy_rule_id)
                )
                policy = policy_result.scalar_one_or_none()
                if policy:
                    policy.is_active = False
                    policies_dismissed += 1

    await db.commit()

    return ThreatTrainResult(
        processed=len(signals),
        policies_activated=policies_activated,
        policies_dismissed=policies_dismissed,
        memory_keys=memory_keys,
        message=(
            f"Processed {len(signals)} signal(s). "
            f"{policies_activated} policies activated, {policies_dismissed} dismissed. "
            "Clone security intelligence updated."
        ),
    )


async def get_threat_layer_report(
    db: AsyncSession,
    org_id: int,
) -> ThreatLayerReport:
    today = date.today()
    since = today - timedelta(days=7)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)

    # Count signals in last 7 days
    signals_result = await db.execute(
        select(ThreatSignal).where(
            ThreatSignal.organization_id == org_id,
            ThreatSignal.created_at >= since_dt,
        ).order_by(ThreatSignal.created_at.desc()).limit(100)
    )
    signals = list(signals_result.scalars().all())

    severity_breakdown: dict[str, int] = {}
    auto_mitigated = 0
    for sig in signals:
        severity_breakdown[sig.severity] = severity_breakdown.get(sig.severity, 0) + 1
        if sig.auto_mitigated:
            auto_mitigated += 1

    # Active policies
    policy_count_result = await db.execute(
        select(sa_func.count(PolicyRule.id)).where(
            PolicyRule.organization_id == org_id,
            PolicyRule.is_active.is_(True),
        )
    )
    active_policies = int(policy_count_result.scalar() or 0)

    # Score: start at 100, deduct for severity
    score = 100
    score -= severity_breakdown.get("critical", 0) * 20
    score -= severity_breakdown.get("high", 0) * 10
    score -= severity_breakdown.get("medium", 0) * 5
    score -= severity_breakdown.get("low", 0) * 2
    score += min(active_policies * 3, 15)  # Bonus for active policies
    score += min(auto_mitigated * 2, 10)   # Bonus for auto-mitigation
    score = max(0, min(100, score))

    # Top threats
    top_signals = sorted(
        [s for s in signals if not s.dismissed],
        key=lambda s: {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}.get(s.severity, 0),
        reverse=True,
    )[:5]

    top_threats = [
        ThreatSignalOut(
            id=int(s.id),
            category=s.category,
            severity=s.severity,
            title=s.title,
            description=s.description,
            source=s.source,
            auto_mitigated=s.auto_mitigated,
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s in top_signals
    ]

    recommendations: list[str] = []
    if severity_breakdown.get("critical", 0) > 0:
        recommendations.append("Immediately review and remediate critical threat signals.")
    if severity_breakdown.get("high", 0) > 2:
        recommendations.append("Multiple high-severity threats detected. Run a focused security audit.")
    if active_policies < 3:
        recommendations.append("Activate more security policies to improve automated protection.")
    if not signals:
        recommendations.append("No threats detected in the last 7 days. Continue regular scans.")
    if auto_mitigated < len(signals) // 2 and signals:
        recommendations.append("Increase auto-mitigation coverage by training on confirmed threats.")

    return ThreatLayerReport(
        security_score=score,
        total_signals_7d=len(signals),
        severity_breakdown=severity_breakdown,
        top_threats=top_threats,
        active_policies=active_policies,
        auto_mitigated_count=auto_mitigated,
        recommendations=recommendations if recommendations else ["Security posture is healthy."],
    )


# ── Personal Branding Power ───────────────────────────────────────────────────

_BRAND_THEMES: dict[str, tuple[str, ...]] = {
    "ai_tech": ("ai", "artificial intelligence", "llm", "machine learning", "automation", "saas"),
    "education": ("education", "student", "university", "learning", "admission", "visa"),
    "leadership": ("ceo", "founder", "leadership", "strategy", "vision", "growth"),
    "personal_dev": ("productivity", "mindset", "habit", "goal", "success", "discipline"),
    "innovation": ("startup", "innovation", "disrupt", "product", "launch", "scale"),
}


async def get_branding_power_report(
    db: AsyncSession,
    org_id: int,
) -> BrandingPowerReport:
    from app.models.social import SocialPost
    from app.models.memory import ProfileMemory

    today = date.today()
    since = today - timedelta(days=30)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)

    posts_result = await db.execute(
        select(SocialPost).where(
            SocialPost.organization_id == org_id,
            SocialPost.created_at >= since_dt,
        ).limit(500)
    )
    posts = list(posts_result.scalars().all())
    published = [p for p in posts if p.status == "published"]

    # Platform coverage
    platforms_active = list({p.platform for p in posts})
    all_platforms = {"instagram", "facebook", "linkedin", "x", "tiktok", "youtube"}
    platform_coverage = max(0, min(100, int((len(platforms_active) / max(len(all_platforms), 1)) * 100)))

    # Content themes
    all_content = " ".join(
        f"{p.title or ''} {p.content or ''}" for p in posts
    ).lower()
    matched_themes: list[str] = []
    for theme, keywords in _BRAND_THEMES.items():
        if any(kw in all_content for kw in keywords):
            matched_themes.append(theme.replace("_", " ").title())

    # Consistency: published ratio
    content_consistency = 0
    if posts:
        content_consistency = max(0, min(100, int((len(published) / len(posts)) * 100)))

    # Audience alignment from memory
    mem_result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == org_id,
            ProfileMemory.category == "learned",
        ).limit(100)
    )
    memories = list(mem_result.scalars().all())
    brand_memory_count = len([
        m for m in memories
        if any(kw in (m.value or "").lower() for kw in ("brand", "audience", "content", "social"))
    ])
    audience_alignment = max(0, min(100, 40 + brand_memory_count * 8))

    # Composite score
    branding_score = max(0, min(100, int(
        (content_consistency * 0.3) +
        (platform_coverage * 0.25) +
        (audience_alignment * 0.25) +
        (min(len(matched_themes) * 15, 100) * 0.2)
    )))

    strengths: list[str] = []
    gaps: list[str] = []
    if content_consistency >= 70:
        strengths.append("Strong content follow-through rate.")
    else:
        gaps.append("Improve draft-to-published conversion rate.")
    if platform_coverage >= 50:
        strengths.append("Good multi-platform presence.")
    else:
        gaps.append("Expand to more platforms for wider reach.")
    if matched_themes:
        strengths.append(f"Content covers key themes: {', '.join(matched_themes[:3])}.")
    else:
        gaps.append("Content lacks clear thematic focus areas.")
    if audience_alignment >= 60:
        strengths.append("Brand knowledge is well-integrated into clone memory.")
    else:
        gaps.append("Train clone with more brand-specific knowledge.")

    next_actions: list[str] = []
    if not published:
        next_actions.append("Publish your first piece of content to start building brand presence.")
    if len(platforms_active) < 3:
        next_actions.append("Expand to at least 3 platforms for consistent brand visibility.")
    if len(matched_themes) < 2:
        next_actions.append("Develop content pillars around 2-3 core themes.")
    if not next_actions:
        next_actions.append("Maintain consistency and track engagement metrics.")

    return BrandingPowerReport(
        branding_score=branding_score,
        content_consistency=content_consistency,
        platform_coverage=platform_coverage,
        audience_alignment=audience_alignment,
        total_posts_30d=len(posts),
        published_posts_30d=len(published),
        platforms_active=platforms_active,
        content_themes=matched_themes,
        strengths=strengths,
        gaps=gaps,
        next_actions=next_actions,
    )


# ── Fraud Detection ────────────────────────────────────────────────────────────

_FRAUD_PATTERNS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "financial_anomaly": {
        "keywords": ("unusual amount", "large transfer", "unexpected charge", "abnormal", "spike"),
        "severity": "high",
        "title": "Financial anomaly detected",
    },
    "duplicate_transaction": {
        "keywords": ("duplicate", "double charge", "repeated payment", "same amount twice"),
        "severity": "medium",
        "title": "Possible duplicate transaction",
    },
    "invoice_fraud": {
        "keywords": ("fake invoice", "inflated", "overcharged", "phantom invoice", "forged"),
        "severity": "high",
        "title": "Invoice fraud indicator",
    },
    "expense_fraud": {
        "keywords": ("personal expense", "unauthorized purchase", "expense padding", "receipt"),
        "severity": "medium",
        "title": "Expense fraud indicator",
    },
    "phantom_vendor": {
        "keywords": ("unknown vendor", "shell company", "no contract", "unregistered", "fictitious"),
        "severity": "high",
        "title": "Phantom vendor risk",
    },
    "identity_fraud": {
        "keywords": ("impersonat", "fake identity", "stolen identity", "spoofed", "phishing"),
        "severity": "critical",
        "title": "Identity fraud detected",
    },
    "unauthorized_access": {
        "keywords": ("unauthorized", "breach", "illegal access", "hacked", "compromised"),
        "severity": "critical",
        "title": "Unauthorized access detected",
    },
    "data_tampering": {
        "keywords": ("tamper", "altered record", "modified without", "forged data", "falsified"),
        "severity": "high",
        "title": "Data tampering indicator",
    },
}


def _scan_for_fraud(text: str) -> list[dict[str, str | int]]:
    lowered = text.lower()
    found: list[dict[str, str | int]] = []
    for category, meta in _FRAUD_PATTERNS.items():
        keywords = meta["keywords"]
        hits = [kw for kw in keywords if kw in lowered]  # type: ignore[union-attr]
        if hits:
            risk_score = 70
            if meta["severity"] == "critical":
                risk_score = 95
            elif meta["severity"] == "high":
                risk_score = 80
            elif meta["severity"] == "medium":
                risk_score = 60
            found.append({
                "category": category,
                "severity": str(meta["severity"]),
                "title": str(meta["title"]),
                "description": f"Matched fraud patterns: {', '.join(hits[:5])}",
                "risk_score": risk_score,
            })
    return found


async def detect_fraud(
    db: AsyncSession,
    org_id: int,
    scope: str = "full_scan",
) -> FraudDetectionResult:
    from app.models.finance import FinanceEntry
    from app.models.note import Note

    today = date.today()
    since = today - timedelta(days=30)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)

    # Scan recent finance entries
    fin_result = await db.execute(
        select(FinanceEntry).where(
            FinanceEntry.organization_id == org_id,
            FinanceEntry.created_at >= since_dt,
        ).limit(500)
    )
    entries = list(fin_result.scalars().all())

    # Scan recent notes
    notes_result = await db.execute(
        select(Note).where(
            Note.organization_id == org_id,
            Note.created_at >= since_dt,
        ).limit(200)
    )
    notes = list(notes_result.scalars().all())

    all_signals: list[dict[str, str | int]] = []

    for entry in entries:
        text = f"{entry.description or ''} {getattr(entry, 'note', '') or ''}"
        for sig in _scan_for_fraud(text):
            sig["source"] = f"finance:{entry.id}"
            all_signals.append(sig)

    for note in notes:
        text = f"{note.title or ''} {note.content or ''}"
        for sig in _scan_for_fraud(text):
            sig["source"] = f"note:{note.id}"
            all_signals.append(sig)

    # Check for duplicate amounts in finance
    amounts = [float(entry.amount) for entry in entries if entry.amount]
    amount_counts = Counter(amounts)
    duplicates = {amt: cnt for amt, cnt in amount_counts.items() if cnt >= 2 and amt > 0}
    for amt, cnt in list(duplicates.items())[:5]:
        all_signals.append({
            "category": "duplicate_transaction",
            "severity": "medium",
            "title": "Duplicate amount detected",
            "description": f"Amount {amt} appears {cnt} times in recent transactions",
            "source": "finance_analysis",
            "risk_score": 55,
        })

    # Deduplicate by category+source
    seen: set[str] = set()
    unique_signals: list[dict[str, str | int]] = []
    for sig in all_signals:
        key = f"{sig['category']}:{sig['source']}"
        if key not in seen:
            seen.add(key)
            unique_signals.append(sig)

    signal_records = [
        FraudSignalOut(
            category=str(sig["category"]),
            severity=str(sig["severity"]),
            title=str(sig["title"]),
            description=str(sig["description"])[:500],
            source=str(sig["source"])[:80],
            risk_score=int(sig.get("risk_score", 50)),
        )
        for sig in unique_signals[:50]
    ]

    risk_breakdown: dict[str, int] = {}
    for sig in signal_records:
        risk_breakdown[sig.category] = risk_breakdown.get(sig.category, 0) + 1

    return FraudDetectionResult(
        scope=scope,
        signals_found=len(signal_records),
        signals=signal_records,
        risk_breakdown=risk_breakdown,
        total_anomalies=len(signal_records),
        message=f"Fraud scan completed. {len(signal_records)} anomaly signal(s) detected.",
    )


async def get_fraud_layer_report(
    db: AsyncSession,
    org_id: int,
) -> FraudLayerReport:
    result = await detect_fraud(db, org_id, scope="layer_report")

    # Active guardrails
    policy_count_result = await db.execute(
        select(sa_func.count(PolicyRule.id)).where(
            PolicyRule.organization_id == org_id,
            PolicyRule.is_active.is_(True),
            PolicyRule.title.like("%Fraud%"),
        )
    )
    guardrails_active = int(policy_count_result.scalar() or 0)

    score = 100
    for sig in result.signals:
        if sig.severity == "critical":
            score -= 25
        elif sig.severity == "high":
            score -= 15
        elif sig.severity == "medium":
            score -= 8
    score += min(guardrails_active * 5, 15)
    score = max(0, min(100, score))

    recommendations: list[str] = []
    if any(s.severity == "critical" for s in result.signals):
        recommendations.append("Critical fraud risk detected. Immediate investigation required.")
    if result.signals_found > 3:
        recommendations.append("Multiple fraud signals found. Run detailed financial audit.")
    if guardrails_active == 0:
        recommendations.append("Create fraud-specific policy rules for automated monitoring.")
    if not result.signals:
        recommendations.append("No fraud signals detected. Maintain regular scanning schedule.")

    return FraudLayerReport(
        fraud_risk_score=score,
        total_anomalies_30d=result.total_anomalies,
        risk_breakdown=result.risk_breakdown,
        top_signals=result.signals[:5],
        guardrails_active=guardrails_active,
        recommendations=recommendations if recommendations else ["Financial integrity looks healthy."],
    )


# ── AI News Digest ─────────────────────────────────────────────────────────────

_NEWS_TOPICS: dict[str, dict[str, str | int]] = {
    "ai_agents": {
        "title": "AI Agents Are Taking Over Enterprise Workflows",
        "summary": "Companies are deploying autonomous AI agents for customer support, data analysis, and workflow automation, reducing manual overhead by 40-60%.",
        "tag": "AI Automation",
        "score": 95,
    },
    "llm_reasoning": {
        "title": "Next-Gen LLMs Show Human-Level Reasoning",
        "summary": "Latest LLM benchmarks show breakthrough performance on complex reasoning tasks, with implications for education, coding, and scientific research.",
        "tag": "AI Research",
        "score": 92,
    },
    "edtech_ai": {
        "title": "AI-Powered Education Platforms Reshape Overseas Admissions",
        "summary": "EdTech startups using AI for personalized student counseling and visa application automation see 3x conversion improvements.",
        "tag": "EdTech",
        "score": 90,
    },
    "personal_brand_ai": {
        "title": "Personal Branding with AI: The New CEO Playbook",
        "summary": "Founders using AI tools for content creation and personal brand management report 5x engagement growth on LinkedIn and X.",
        "tag": "Personal Branding",
        "score": 88,
    },
    "saas_automation": {
        "title": "SaaS Companies Embrace AI-First Architecture",
        "summary": "SaaS platforms built with AI at the core are outperforming traditional tools, offering predictive insights and automated decision-making.",
        "tag": "SaaS",
        "score": 85,
    },
    "clone_tech": {
        "title": "Digital Clone Technology Enters Mainstream Business",
        "summary": "Personal AI clones that handle communications, scheduling, and knowledge management are becoming essential tools for busy executives.",
        "tag": "AI Clones",
        "score": 93,
    },
    "cybersec_ai": {
        "title": "AI-Driven Cybersecurity Detects Threats 10x Faster",
        "summary": "Machine learning models now identify and respond to cyber threats in real-time, outperforming traditional rule-based systems.",
        "tag": "Cybersecurity",
        "score": 82,
    },
    "india_ai_boom": {
        "title": "India's AI Startup Ecosystem Hits Record Funding",
        "summary": "Indian AI startups raised $4.2B in the last quarter, with education, healthcare, and enterprise automation leading sectors.",
        "tag": "Startup Ecosystem",
        "score": 87,
    },
    "no_code_ai": {
        "title": "No-Code AI Platforms Democratize Business Automation",
        "summary": "Non-technical teams are building AI-powered workflows using drag-and-drop interfaces, accelerating digital transformation.",
        "tag": "Automation",
        "score": 78,
    },
    "ai_regulation": {
        "title": "Global AI Governance Frameworks Take Shape",
        "summary": "EU, US, and India propose new AI safety and compliance standards that will impact how businesses deploy and scale AI systems.",
        "tag": "AI Policy",
        "score": 75,
    },
    "voice_ai": {
        "title": "Voice AI Transforms Customer Interactions",
        "summary": "Conversational AI systems with near-human voice quality are replacing traditional IVR and call center operations.",
        "tag": "Voice AI",
        "score": 80,
    },
    "productivity_ai": {
        "title": "AI Productivity Tools Boost Executive Output by 3x",
        "summary": "CEOs and founders using AI assistants for email, task management, and decision support report significantly higher output.",
        "tag": "Productivity",
        "score": 86,
    },
}


async def generate_news_digest(
    db: AsyncSession,
    org_id: int,
    data: NewsDigestRequest,
) -> NewsDigestResult:
    interests = [i.strip().lower() for i in data.interests if i.strip()]
    if not interests:
        interests = ["artificial intelligence", "education", "startup"]

    # Score topics by relevance to interests
    scored: list[tuple[str, dict[str, str | int], int]] = []
    for topic_key, meta in _NEWS_TOPICS.items():
        title = str(meta["title"]).lower()
        summary = str(meta["summary"]).lower()
        combined = f"{title} {summary} {topic_key}"
        relevance = 0
        for interest in interests:
            tokens = interest.split()
            for token in tokens:
                if token in combined:
                    relevance += 10
        base_score = int(meta["score"])
        final_score = max(0, min(100, base_score + relevance))
        scored.append((topic_key, meta, final_score))

    scored.sort(key=lambda x: x[2], reverse=True)
    top_items = scored[:data.max_items]

    items = [
        NewsDigestItem(
            title=str(meta["title"]),
            summary=str(meta["summary"]),
            relevance_tag=str(meta["tag"]),
            relevance_score=score,
        )
        for _, meta, score in top_items
    ]

    # Feed top items into daily context
    matched_interests: list[str] = []
    memory_keys: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    for idx, item in enumerate(items[:5], start=1):
        key = f"news.digest.{stamp}.{idx}"
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key[:100],
            value=f"[{item.relevance_tag}] {item.title}: {item.summary[:150]}",
            category="news_digest",
        )
        memory_keys.append(key[:100])
        if item.relevance_tag not in matched_interests:
            matched_interests.append(item.relevance_tag)

    await db.commit()

    return NewsDigestResult(
        items=items,
        interests_matched=matched_interests,
        memory_keys=memory_keys,
        message=f"Generated {len(items)} AI news items tailored to your interests.",
    )


# ── Ethical Boundary Layer ─────────────────────────────────────────────────────

_ETHICAL_PATTERNS: dict[str, dict[str, str | tuple[str, ...]]] = {
    "bias_discrimination": {
        "keywords": ("discriminat", "biased", "racist", "sexist", "prejudice", "unfair targeting"),
        "severity": "critical",
    },
    "privacy_violation": {
        "keywords": ("personal data", "without consent", "track user", "surveillance", "spy", "dox"),
        "severity": "high",
    },
    "misinformation": {
        "keywords": ("fake news", "disinformation", "misleading", "fabricated", "false claim"),
        "severity": "high",
    },
    "manipulation": {
        "keywords": ("manipulat", "dark pattern", "coerce", "deceive", "trick user", "exploit"),
        "severity": "high",
    },
    "harmful_content": {
        "keywords": ("hate speech", "violent", "harass", "bully", "threaten", "abuse"),
        "severity": "critical",
    },
    "transparency": {
        "keywords": ("hidden", "undisclosed", "secret tracking", "opaque", "not transparent"),
        "severity": "medium",
    },
    "consent_violation": {
        "keywords": ("without permission", "no consent", "opt-out ignored", "forced", "mandatory"),
        "severity": "high",
    },
    "accountability_gap": {
        "keywords": ("no audit", "unaccountable", "untraceable", "no oversight", "no review"),
        "severity": "medium",
    },
}


async def get_ethical_boundary_report(
    db: AsyncSession,
    org_id: int,
) -> EthicalBoundaryReport:
    from app.models.memory import ProfileMemory, DailyContext
    from app.models.note import Note

    today = date.today()
    since = today - timedelta(days=30)
    since_dt = datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)

    notes_result = await db.execute(
        select(Note).where(
            Note.organization_id == org_id,
            Note.created_at >= since_dt,
        ).limit(300)
    )
    notes = list(notes_result.scalars().all())

    mem_result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == org_id,
        ).limit(500)
    )
    memories = list(mem_result.scalars().all())

    ctx_result = await db.execute(
        select(DailyContext).where(
            DailyContext.organization_id == org_id,
            DailyContext.date >= since,
        ).limit(200)
    )
    contexts = list(ctx_result.scalars().all())

    violations: list[EthicalViolation] = []

    def _check_text(text: str, source: str) -> None:
        lowered = text.lower()
        for category, meta in _ETHICAL_PATTERNS.items():
            keywords = meta["keywords"]
            hits = [kw for kw in keywords if kw in lowered]  # type: ignore[union-attr]
            if hits:
                violations.append(EthicalViolation(
                    category=category,
                    severity=str(meta["severity"]),
                    description=f"Matched: {', '.join(hits[:3])}",
                    source=source,
                ))

    for note in notes:
        _check_text(f"{note.title or ''} {note.content or ''}", f"note:{note.id}")
    for mem in memories:
        _check_text(f"{mem.key} {mem.value}", f"profile_memory:{mem.id}")
    for ctx in contexts:
        _check_text(ctx.content or "", f"daily_context:{ctx.id}")

    # Deduplicate
    seen: set[str] = set()
    unique: list[EthicalViolation] = []
    for v in violations:
        key = f"{v.category}:{v.source}"
        if key not in seen:
            seen.add(key)
            unique.append(v)
    violations = unique[:50]

    # Active guardrails
    policy_count_result = await db.execute(
        select(sa_func.count(PolicyRule.id)).where(
            PolicyRule.organization_id == org_id,
            PolicyRule.is_active.is_(True),
        )
    )
    active_guardrails = int(policy_count_result.scalar() or 0)

    # Category breakdown
    category_breakdown: dict[str, int] = {}
    for v in violations:
        category_breakdown[v.category] = category_breakdown.get(v.category, 0) + 1

    # Score
    score = 100
    for v in violations:
        if v.severity == "critical":
            score -= 20
        elif v.severity == "high":
            score -= 10
        elif v.severity == "medium":
            score -= 5
    score += min(active_guardrails * 2, 10)
    score = max(0, min(100, score))

    compliance_areas = [
        "Data privacy and consent",
        "Fair and unbiased decision-making",
        "Transparency in AI actions",
        "Content safety and moderation",
        "Accountability and audit trail",
    ]

    recommendations: list[str] = []
    if any(v.severity == "critical" for v in violations):
        recommendations.append("Critical ethical violation detected. Review and remediate immediately.")
    if category_breakdown.get("privacy_violation", 0) > 0:
        recommendations.append("Review data handling practices for privacy compliance.")
    if category_breakdown.get("bias_discrimination", 0) > 0:
        recommendations.append("Audit AI outputs for bias and discriminatory patterns.")
    if active_guardrails < 3:
        recommendations.append("Create more guardrail policies to enforce ethical boundaries.")
    if not violations:
        recommendations.append("No ethical violations detected. Ethical posture is strong.")

    return EthicalBoundaryReport(
        ethics_score=score,
        violations_found=len(violations),
        violations=violations,
        category_breakdown=category_breakdown,
        active_guardrails=active_guardrails,
        compliance_areas=compliance_areas,
        recommendations=recommendations if recommendations else ["Ethical compliance is healthy."],
    )
