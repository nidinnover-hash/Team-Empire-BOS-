from __future__ import annotations

import re

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
