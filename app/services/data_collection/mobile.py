from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_rule import PolicyRule
from app.schemas.data_collection import (
    MobileCaptureAnalyzeRequest,
    MobileCaptureAnalyzeResult,
)
from app.schemas.memory import DailyContextCreate
from app.schemas.note import NoteCreate
from app.services import memory as memory_service
from app.services import note as note_service
from app.services.data_collection._shared import (
    _MAX_ITEM_CHARS,
    _UNWANTED_HINTS,
    _WANTED_HINTS,
)

logger = logging.getLogger(__name__)


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
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
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
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.debug("Topic token JSON parse failed: %s", type(exc).__name__)
    tokens = re.split(r"[,;\n]", text)
    return [tok.strip() for tok in tokens if tok.strip()][:20]


def extract_text_from_image_bytes(image_bytes: bytes) -> tuple[str, str]:
    if not image_bytes:
        raise ValueError("empty image payload")
    try:
        from PIL import Image
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - dependency availability
        raise RuntimeError(
            "Pillow is required for image OCR. Install with: pip install pillow"
        ) from exc
    try:
        import pytesseract
    except (ImportError, ModuleNotFoundError) as exc:  # pragma: no cover - dependency availability
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
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("invalid image payload") from exc

    text = (pytesseract.image_to_string(image) or "").strip()
    if not text:
        raise ValueError("no text detected in image")
    return text, "pytesseract"
