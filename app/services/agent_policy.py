from __future__ import annotations

import re
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.action_types import CANONICAL_AGENT_ACTIONS, normalize_action_type
from app.models.policy_rule import PolicyRule

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "must", "should",
    "would", "could", "about", "your", "their", "there", "where", "when", "what",
    "which", "while", "then", "than", "have", "has", "had", "been", "were", "will",
}

_MEMORY_SECRET_RE = re.compile(
    r"\b(password|passcode|otp|secret|api key|token|private key|client secret)\b",
    flags=re.IGNORECASE,
)

_RULE_BLOCK_RE = re.compile(
    r"\b(block|forbid|forbidden|never|do not|don't|must not|deny)\b",
    flags=re.IGNORECASE,
)


class PolicyEvaluation(TypedDict):
    policy_score: int
    blocked_actions: list[str]
    blocked_by_policy: bool
    reasons: list[str]
    matched_rule_ids: list[int]


def _extract_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return {w for w in words if len(w) >= 5 and w not in _STOPWORDS}


async def evaluate_agent_policy(
    db: AsyncSession,
    *,
    organization_id: int,
    message: str,
    proposed_actions: list[str],
) -> PolicyEvaluation:
    msg = (message or "").strip().lower()
    msg_keywords = _extract_keywords(msg)
    actions = {
        normalize_action_type(a)
        for a in proposed_actions
        if normalize_action_type(a) in CANONICAL_AGENT_ACTIONS
    }
    reasons: list[str] = []
    matched_rule_ids: list[int] = []
    blocked_actions: set[str] = set()
    score = 100

    rows = (
        await db.execute(
            select(PolicyRule).where(
                PolicyRule.organization_id == organization_id,
                PolicyRule.is_active.is_(True),
            ).limit(500)
        )
    ).scalars().all()

    for row in rows:
        corpus = f"{row.title} {row.rule_text}"
        keywords = _extract_keywords(corpus)
        if not keywords:
            continue
        overlap = msg_keywords.intersection(keywords)
        if len(overlap) >= 2:
            matched_rule_ids.append(int(row.id))
            score -= 7
            reasons.append(f"Policy matched: {row.title} ({len(overlap)} shared terms)")
            if _RULE_BLOCK_RE.search(corpus):
                if "MEMORY_WRITE" in actions and ("memory" in corpus.lower() or "secret" in corpus.lower()):
                    blocked_actions.add("MEMORY_WRITE")
                for risky in ("SEND_MESSAGE", "SPEND_MONEY", "DELETE_DATA", "ASSIGN_LEADS", "CHANGE_CRM_STATUS"):
                    if risky in actions:
                        blocked_actions.add(risky)

    if "MEMORY_WRITE" in actions and _MEMORY_SECRET_RE.search(msg):
        blocked_actions.add("MEMORY_WRITE")
        reasons.append("Sensitive secret-like content blocked from memory write.")
        score -= 20

    if blocked_actions:
        score = min(score, 40)
    if not rows:
        reasons.append("No active policy rules; baseline guardrails only.")
    score = max(0, min(100, score))

    return {
        "policy_score": int(score),
        "blocked_actions": sorted(blocked_actions),
        "blocked_by_policy": bool(blocked_actions),
        "reasons": reasons[:6],
        "matched_rule_ids": matched_rule_ids[:20],
    }
