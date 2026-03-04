"""
Conversation learning service.

Extracts explicit user preferences from chat messages and stores them as
profile memory so the clone adapts over time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.logs.audit import record_action
from app.services import memory as memory_service

_MAX_VALUE_LEN = 220
_MAX_NAME_LEN = 60


@dataclass(frozen=True)
class LearnedSignal:
    key: str
    value: str
    category: str = "learned"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(password|passcode|otp|secret|api key|token|private key)\b", lowered):
        return True
    return "@" in text


def extract_learning_signals(message: str) -> list[LearnedSignal]:
    """
    Parse explicit preference-style statements from user text.
    Conservative on purpose: only captures clear first-person intent.
    """
    msg = _clean_text(message)
    if len(msg) < 8:
        return []

    signals: list[LearnedSignal] = []
    lowered = msg.lower()

    m_name = re.search(r"\bcall me\s+([A-Za-z][A-Za-z .'\-]{1,60}?)(?:[.?!]|$)", msg, flags=re.IGNORECASE)
    if m_name:
        name = _clean_text(m_name.group(1))[:_MAX_NAME_LEN]
        if name:
            signals.append(LearnedSignal(key="identity.preferred_name", value=name))

    m_prefer = re.search(r"\bi prefer\s+(.+?)(?:[.?!]|$)", msg, flags=re.IGNORECASE)
    if m_prefer:
        pref = _clean_text(m_prefer.group(1))[:_MAX_VALUE_LEN]
        if pref and not _looks_sensitive(pref):
            signals.append(LearnedSignal(key="preference.general", value=pref))

    m_dislike = re.search(r"\bi (?:do not|don't) like\s+(.+?)(?:[.?!]|$)", msg, flags=re.IGNORECASE)
    if m_dislike:
        avoid = _clean_text(m_dislike.group(1))[:_MAX_VALUE_LEN]
        if avoid and not _looks_sensitive(avoid):
            signals.append(LearnedSignal(key="preference.avoid", value=avoid))

    m_priority = re.search(r"\bmy (?:top )?priority is\s+(.+?)(?:[.?!]|$)", msg, flags=re.IGNORECASE)
    if m_priority:
        priority = _clean_text(m_priority.group(1))[:_MAX_VALUE_LEN]
        if priority and not _looks_sensitive(priority):
            signals.append(LearnedSignal(key="work.priority_focus", value=priority))

    m_workstyle = re.search(r"\bi work best\s+(.+?)(?:[.?!]|$)", msg, flags=re.IGNORECASE)
    if m_workstyle:
        style = _clean_text(m_workstyle.group(1))[:_MAX_VALUE_LEN]
        if style and not _looks_sensitive(style):
            signals.append(LearnedSignal(key="work.style", value=style))

    # If message asks to remember/learn/train something explicit, keep the statement.
    for trigger in ("remember", "learn", "train", "note that", "know that"):
        if trigger not in lowered:
            continue
        m_remember = re.search(
            r"\b(?:remember|learn|train|note that|know that)(?: that)?\s+(.+?)(?:[.?!]|$)",
            msg, flags=re.IGNORECASE,
        )
        if m_remember:
            fact = _clean_text(m_remember.group(1))[:_MAX_VALUE_LEN]
            if fact and not _looks_sensitive(fact):
                signals.append(LearnedSignal(key="memory.explicit_fact", value=fact))
            break

    # Keep last value when same key appears multiple times.
    dedup: dict[str, LearnedSignal] = {s.key: s for s in signals}
    return list(dedup.values())


async def learn_from_message(
    db: AsyncSession,
    org_id: int,
    actor_user_id: int | None,
    message: str,
) -> int:
    if not settings.CLONE_AUTO_LEARN_FROM_CHAT:
        return 0

    signals = extract_learning_signals(message)
    written = 0
    for s in signals:
        entry = await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=s.key,
            value=s.value,
            category=s.category,
        )
        await record_action(
            db=db,
            event_type="chat_memory_learned",
            actor_user_id=actor_user_id,
            organization_id=org_id,
            entity_type="profile_memory",
            entity_id=entry.id,
            payload_json={"key": s.key},
        )
        written += 1
    return written
