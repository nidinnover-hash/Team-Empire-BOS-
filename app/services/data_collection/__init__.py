"""data_collection service package.

Re-exports every public (and test-visible private) symbol so that
existing imports continue to work unchanged:

    from app.services import data_collection as data_collection_service
    from app.services.data_collection import get_threat_layer_report
"""

from __future__ import annotations

# ── logging (module-level logger used by mobile.py) ────────────────────────────
import logging

# ── shared helpers / constants (some used by tests) ────────────────────────────
from app.services.data_collection._shared import (
    _ALLOWED_CONTEXT_TYPES,
    _CLOSE_WORDS,
    _EMPATHY_WORDS,
    _FILLER_WORDS,
    _KEY_PATTERN,
    _MAX_ITEM_CHARS,
    _MAX_ITEMS,
    _MAX_PRO_ITEM_CHARS,
    _OBJECTION_WORDS,
    _UNWANTED_HINTS,
    _WANTED_HINTS,
    _normalize_items,
    _normalize_pro_items,
)

# ── branding ───────────────────────────────────────────────────────────────────
from app.services.data_collection.branding import (
    _BRAND_THEMES,
    get_branding_power_report,
)

# ── character study ────────────────────────────────────────────────────────────
from app.services.data_collection.character import (
    _CHARACTER_TRAIT_KEYWORDS,
    _character_confidence,
    _extract_character_traits,
    analyze_photo_character,
)

# ── coaching ───────────────────────────────────────────────────────────────────
from app.services.data_collection.coaching import (
    _coaching_sentences,
    analyze_meeting_transcript,
)

# ── ethics ─────────────────────────────────────────────────────────────────────
from app.services.data_collection.ethics import (
    _ETHICAL_PATTERNS,
    get_ethical_boundary_report,
)

# ── fraud ──────────────────────────────────────────────────────────────────────
from app.services.data_collection.fraud import (
    _FRAUD_PATTERNS,
    _scan_for_fraud,
    detect_fraud,
    get_fraud_layer_report,
)

# ── ingest ─────────────────────────────────────────────────────────────────────
from app.services.data_collection.ingest import (
    ingest_data,
    train_clone_pro,
)

# ── media ──────────────────────────────────────────────────────────────────────
from app.services.data_collection.media import (
    _QUALITY_KEYWORDS,
    _score_media_quality,
    create_media_project,
    get_media_editing_layer,
)

# ── mobile / OCR ───────────────────────────────────────────────────────────────
from app.services.data_collection.mobile import (
    _mobile_lines,
    _score_line,
    analyze_mobile_capture,
    extract_text_from_image_bytes,
    parse_topic_tokens,
)

# ── news ───────────────────────────────────────────────────────────────────────
from app.services.data_collection.news import (
    _NEWS_TOPICS,
    generate_news_digest,
)

# ── social ─────────────────────────────────────────────────────────────────────
from app.services.data_collection.social import (
    get_social_management_layer,
)

# ── threats ────────────────────────────────────────────────────────────────────
from app.services.data_collection.threats import (
    _THREAT_PATTERNS,
    _scan_text_for_threats,
    detect_threats,
    get_threat_layer_report,
    train_threat_signals,
)

logger = logging.getLogger(__name__)

__all__ = [
    # shared
    "_ALLOWED_CONTEXT_TYPES",
    # branding
    "_BRAND_THEMES",
    # character
    "_CHARACTER_TRAIT_KEYWORDS",
    "_CLOSE_WORDS",
    "_EMPATHY_WORDS",
    # ethics
    "_ETHICAL_PATTERNS",
    "_FILLER_WORDS",
    # fraud
    "_FRAUD_PATTERNS",
    "_KEY_PATTERN",
    "_MAX_ITEMS",
    "_MAX_ITEM_CHARS",
    "_MAX_PRO_ITEM_CHARS",
    # news
    "_NEWS_TOPICS",
    "_OBJECTION_WORDS",
    # media
    "_QUALITY_KEYWORDS",
    # threats
    "_THREAT_PATTERNS",
    "_UNWANTED_HINTS",
    "_WANTED_HINTS",
    "_character_confidence",
    # coaching
    "_coaching_sentences",
    "_extract_character_traits",
    # mobile
    "_mobile_lines",
    "_normalize_items",
    "_normalize_pro_items",
    "_scan_for_fraud",
    "_scan_text_for_threats",
    "_score_line",
    "_score_media_quality",
    "analyze_meeting_transcript",
    "analyze_mobile_capture",
    "analyze_photo_character",
    "create_media_project",
    "detect_fraud",
    "detect_threats",
    "extract_text_from_image_bytes",
    "generate_news_digest",
    "get_branding_power_report",
    "get_ethical_boundary_report",
    "get_fraud_layer_report",
    "get_media_editing_layer",
    # social
    "get_social_management_layer",
    "get_threat_layer_report",
    # ingest
    "ingest_data",
    # logger
    "logger",
    "parse_topic_tokens",
    "train_clone_pro",
    "train_threat_signals",
]
