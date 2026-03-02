"""Cross-layer intelligence — correlates signals across all business layers."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def analyze_cross_layer(
    db: AsyncSession,
    org_id: int,
    window_days: int = 30,
) -> dict:
    """Run cross-layer correlation analysis and generate strategic insights."""
    from app.services.layers_pkg import clone, marketing, people

    scores: dict[str, float | None] = {}
    insights: list[dict] = []
    contradictions: list[str] = []

    # Collect layer scores safely
    try:
        mktg = await marketing.get_marketing_layer(db, org_id, window_days)
        scores["marketing"] = float(mktg.readiness_score)
        scores["ad_spend"] = mktg.ad_spend_in_window
        scores["revenue"] = mktg.revenue_in_window
        scores["new_contacts"] = float(mktg.new_business_contacts)
    except Exception:
        logger.warning("cross_layer: marketing layer failed org=%d", org_id, exc_info=True)

    try:
        study = await marketing.get_study_layer(db, org_id, window_days)
        scores["study_score"] = float(study.operational_score)
        scores["study_pipeline"] = float(study.study_pipeline_contacts)
    except Exception:
        logger.warning("cross_layer: study layer failed org=%d", org_id, exc_info=True)

    try:
        training = await people.get_training_layer(db, org_id, window_days)
        scores["training_score"] = float(training.training_score)
        scores["avg_ai_level"] = training.avg_ai_level
    except Exception:
        logger.warning("cross_layer: training layer failed org=%d", org_id, exc_info=True)

    try:
        emp_perf = await people.get_employee_performance_layer(db, org_id, window_days)
        scores["performance_score"] = float(emp_perf.performance_score)
        scores["overdue_tasks"] = float(emp_perf.overdue_operational_tasks)
    except Exception:
        logger.warning("cross_layer: performance layer failed org=%d", org_id, exc_info=True)

    try:
        revenue = await people.get_revenue_management_layer(db, org_id, window_days)
        scores["revenue_health"] = float(revenue.revenue_health_score)
        scores["net_revenue"] = revenue.net_in_window
    except Exception:
        logger.warning("cross_layer: revenue layer failed org=%d", org_id, exc_info=True)

    try:
        emp_mgmt = await people.get_employee_management_layer(db, org_id, window_days)
        scores["management_score"] = float(emp_mgmt.management_score)
        scores["unmapped_employees"] = float(emp_mgmt.unmapped_employees)
    except Exception:
        logger.warning("cross_layer: management layer failed org=%d", org_id, exc_info=True)

    try:
        clone_layer = await clone.get_clone_training_layer(db, org_id, window_days)
        scores["clone_training_score"] = float(clone_layer.clone_training_score)
        scores["missing_profiles"] = float(clone_layer.missing_profile_employees)
    except Exception:
        logger.warning("cross_layer: clone layer failed org=%d", org_id, exc_info=True)

    try:
        prosperity_layer = await people.get_staff_prosperity_layer(db, org_id, window_days)
        scores["prosperity_composite"] = float(prosperity_layer.composite_score)
    except Exception:
        logger.warning("cross_layer: prosperity layer failed org=%d", org_id, exc_info=True)

    # Cross-layer contradiction detection
    ad_spend = scores.get("ad_spend", 0) or 0
    mktg_score = scores.get("marketing")
    clone_score = scores.get("clone_training_score")
    perf_score = scores.get("performance_score")
    overdue = scores.get("overdue_tasks", 0) or 0
    net_rev = scores.get("net_revenue")
    ai_level = scores.get("avg_ai_level", 0) or 0
    study_pipeline = scores.get("study_pipeline", 0) or 0
    prosperity_score = scores.get("prosperity_composite")

    if ad_spend > 0 and clone_score is not None and clone_score < 60:
        contradictions.append(
            "Marketing spend is active but sales clone readiness is low — "
            "train clones before scaling ad spend."
        )
        insights.append({
            "type": "contradiction",
            "layers": ["marketing", "clone_training"],
            "insight": "Ad spend without clone readiness wastes budget. Train sales clones first.",
            "priority": "high",
            "action": "Pause non-essential ad spend, run clone training sprint for sales team.",
        })

    if net_rev is not None and net_rev < 0 and overdue > 5:
        contradictions.append(
            "Revenue is negative while task backlog is growing — operational bottleneck."
        )
        insights.append({
            "type": "contradiction",
            "layers": ["revenue", "performance"],
            "insight": "Negative revenue combined with growing overdue tasks signals execution breakdown.",
            "priority": "critical",
            "action": "48-hour recovery sprint: clear overdue tasks and fix revenue pipeline.",
        })

    if study_pipeline > 10 and ai_level < 2.5:
        contradictions.append(
            "Study pipeline is growing but team AI maturity is low — capacity risk."
        )
        insights.append({
            "type": "risk",
            "layers": ["study", "training"],
            "insight": "Growing pipeline without AI-ready team creates bottleneck risk.",
            "priority": "high",
            "action": "Prioritize AI training for counselor team to handle pipeline growth.",
        })

    if (
        perf_score is not None
        and perf_score < 50
        and prosperity_score is not None
        and prosperity_score > 70
    ):
        contradictions.append(
            "Performance is low but prosperity index is high — metrics may not reflect reality."
        )
        insights.append({
            "type": "data_quality",
            "layers": ["performance", "prosperity"],
            "insight": "Disconnect between performance and prosperity suggests data gaps.",
            "priority": "medium",
            "action": "Audit performance data sources and verify metric accuracy.",
        })

    if mktg_score is not None and mktg_score > 80 and scores.get("new_contacts", 0) == 0:
        insights.append({
            "type": "opportunity",
            "layers": ["marketing"],
            "insight": "Marketing readiness is high but no new contacts — increase outreach.",
            "priority": "high",
            "action": "Launch targeted outreach campaign this week.",
        })

    if clone_score is not None and clone_score > 80 and perf_score is not None and perf_score > 80:
        insights.append({
            "type": "strength",
            "layers": ["clone_training", "performance"],
            "insight": "Clone readiness and performance are both strong — ready to scale operations.",
            "priority": "low",
            "action": "Consider expanding team capacity or taking on bigger projects.",
        })

    # Composite health
    scored = [v for v in scores.values() if isinstance(v, float) and 0 <= v <= 100]
    composite = round(sum(scored) / len(scored), 1) if scored else 0.0

    return {
        "window_days": window_days,
        "layer_scores": {k: round(v, 2) if isinstance(v, float) else v for k, v in scores.items()},
        "composite_health": composite,
        "insights": insights[:10],
        "contradictions": contradictions[:5],
        "layers_analyzed": len(scores),
    }
