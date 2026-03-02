"""CTO Strategic Mode — Claude analyzes full system state and generates strategic plan."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def run_strategic_review(
    db: AsyncSession,
    org_id: int,
    challenge: str = "",
    window_days: int = 30,
) -> dict:
    """Run a full CTO-level strategic review using Claude."""
    from app.services.cross_layer_intelligence import analyze_cross_layer
    from app.services.learning_feedback import get_learning_insights
    from app.services.self_learning import learning_signals

    # 1. Cross-layer analysis
    try:
        cross = await analyze_cross_layer(db, org_id, window_days)
    except Exception:
        logger.warning("cto_review: cross-layer failed org=%d", org_id, exc_info=True)
        cross = {"layer_scores": {}, "insights": [], "composite_health": 0}

    # 2. Learning signals
    try:
        signals = await learning_signals(
            db,
            organization_id=org_id,
            lookback_days=window_days,
        )
    except Exception:
        logger.warning("cto_review: learning signals failed org=%d", org_id, exc_info=True)
        signals = {}

    # 3. Learning effectiveness
    try:
        effectiveness = await get_learning_insights(db, org_id, days=window_days)
    except Exception:
        logger.warning("cto_review: learning insights failed org=%d", org_id, exc_info=True)
        effectiveness = {}

    # 4. Clone summary
    try:
        from app.services.clone_brain import clone_org_summary
        clone_summary = await clone_org_summary(
            db,
            organization_id=org_id,
            week_start_date=None,
        )
    except Exception:
        logger.warning("cto_review: clone summary failed org=%d", org_id, exc_info=True)
        clone_summary = {}

    # 5. Policy effectiveness
    try:
        from app.services.policy_effectiveness import get_policy_effectiveness
        policies = await get_policy_effectiveness(db, org_id, weeks=4)
    except Exception:
        logger.warning("cto_review: policy effectiveness failed org=%d", org_id, exc_info=True)
        policies = {}

    # Build diagnostic payload for Claude
    diagnostics = {
        "composite_health": cross.get("composite_health", 0),
        "layer_scores": cross.get("layer_scores", {}),
        "contradictions": cross.get("contradictions", []),
        "top_insights": cross.get("insights", [])[:5],
        "clone_summary": clone_summary,
        "learning_intelligence_score": signals.get("learning_intelligence_score", 0),
        "coaching_effectiveness": effectiveness,
        "policy_summary": policies.get("summary", ""),
        "policy_recommendations": policies.get("recommendations", [])[:3],
        "challenge": challenge,
    }

    # Call Claude for strategic plan
    strategic_plan = ""
    provider_used = "rule_based_fallback"
    try:
        from app.services.ai_router import call_ai

        system_prompt = (
            "You are Claude, acting as CTO of a fast-growing business operating system. "
            "You have full access to all business data. Analyze the diagnostics and generate:\n"
            "1. **System Health Assessment** (1-2 sentences)\n"
            "2. **7-Day Priorities** (top 3 actions)\n"
            "3. **30-Day Roadmap** (top 5 strategic moves)\n"
            "4. **Resource Allocation** (where to focus team energy)\n"
            "5. **Innovation Bets** (2 data-driven experiments to run)\n"
            "6. **Risk Alerts** (anything that needs immediate CEO attention)\n"
            "Every recommendation MUST cite specific data from the diagnostics. "
            "Be concise, actionable, and strictly data-driven."
        )
        import json
        strategic_plan = await call_ai(
            system_prompt=system_prompt,
            user_message=json.dumps(diagnostics, default=str),
            provider="anthropic",
            max_tokens=1200,
        )
        provider_used = "anthropic"
    except Exception:
        logger.debug("CTO strategic AI call failed, using rule-based", exc_info=True)
        # Rule-based fallback
        priorities: list[str] = []
        health = diagnostics["composite_health"]
        if health < 50:
            priorities.append("CRITICAL: Composite health below 50 — run emergency triage across all layers.")
        for insight in diagnostics["top_insights"][:3]:
            priorities.append(f"{insight.get('priority', 'medium').upper()}: {insight.get('action', '')}")
        for rec in diagnostics["policy_recommendations"][:2]:
            priorities.append(f"POLICY: {rec.get('action', '')}")
        if not priorities:
            priorities.append("System is healthy. Focus on growth experiments and team capability building.")
        strategic_plan = "\n".join(f"- {p}" for p in priorities)

    # Extract actionable next steps
    next_actions: list[str] = []
    for insight in cross.get("insights", [])[:3]:
        action = insight.get("action", "")
        if action:
            next_actions.append(action)
    for rec in policies.get("recommendations", [])[:2]:
        action = rec.get("action", "")
        if action:
            next_actions.append(action)
    if not next_actions:
        next_actions.append("Continue current execution and monitor layer scores weekly.")

    return {
        "ok": True,
        "provider": provider_used,
        "composite_health": diagnostics["composite_health"],
        "strategic_plan": strategic_plan,
        "diagnostics": diagnostics,
        "next_actions": next_actions[:7],
        "challenge": challenge,
        "window_days": window_days,
    }
