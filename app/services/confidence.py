from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ConfidenceAssessment:
    score: int
    level: str
    reasons: list[str]
    needs_human_review: bool


def assess_agent_confidence(
    *,
    user_message: str,
    ai_response: str,
    requires_approval: bool,
    memory_context: str,
    proposed_actions_count: int,
) -> ConfidenceAssessment:
    score = 50
    reasons: list[str] = []

    if memory_context.strip():
        score += 15
        reasons.append("Memory context was available.")
    else:
        score -= 10
        reasons.append("No memory context was available.")

    if ai_response.startswith("Error:"):
        score -= 35
        reasons.append("LLM provider returned an error.")
    elif len(ai_response.strip()) >= 80:
        score += 10
        reasons.append("Response has sufficient detail.")
    else:
        score -= 5
        reasons.append("Response is short and may be incomplete.")

    risky_tokens = ("send", "delete", "shutdown", "deploy", "fire", "hire", "pay")
    if any(token in user_message.lower() for token in risky_tokens):
        score -= 10
        reasons.append("Request includes high-risk action keywords.")

    if proposed_actions_count > 0:
        score += 5
        reasons.append("Structured actions were identified.")

    if requires_approval:
        score -= 8
        reasons.append("Action requires manual approval.")

    score = max(0, min(100, score))
    if score >= 80:
        level = "high"
    elif score >= 60:
        level = "medium"
    else:
        level = "low"

    needs_human_review = requires_approval or score < 60 or ai_response.startswith("Error:")
    return ConfidenceAssessment(
        score=score,
        level=level,
        reasons=reasons[:5],
        needs_human_review=needs_human_review,
    )
