"""Layer score snapshots — persist weekly scores and serve trend data."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.layer_score_snapshot import LayerScoreSnapshot

logger = logging.getLogger(__name__)

# Layers to snapshot and their score-extraction functions
_LAYER_CONFIGS: list[tuple[str, str, str]] = [
    ("marketing", "app.services.layers_pkg.marketing", "get_marketing_layer"),
    ("study", "app.services.layers_pkg.marketing", "get_study_layer"),
    ("training", "app.services.layers_pkg.people", "get_training_layer"),
    ("employee_performance", "app.services.layers_pkg.people", "get_employee_performance_layer"),
    ("employee_management", "app.services.layers_pkg.people", "get_employee_management_layer"),
    ("revenue", "app.services.layers_pkg.people", "get_revenue_management_layer"),
    ("staff_training", "app.services.layers_pkg.people", "get_staff_training_layer"),
    ("prosperity", "app.services.layers_pkg.people", "get_staff_prosperity_layer"),
    ("clone_training", "app.services.layers_pkg.clone", "get_clone_training_layer"),
]

_SCORE_FIELD_MAP: dict[str, str] = {
    "marketing": "readiness_score",
    "study": "operational_score",
    "training": "training_score",
    "employee_performance": "performance_score",
    "employee_management": "management_score",
    "revenue": "revenue_health_score",
    "staff_training": "training_velocity_score",
    "prosperity": "composite_score",
    "clone_training": "clone_training_score",
}


async def snapshot_all_layers(
    db: AsyncSession,
    org_id: int,
    window_days: int = 30,
) -> dict:
    """Capture current scores for all layers and persist snapshots."""
    import importlib

    written = 0
    skipped = 0
    errors = 0
    now = datetime.now(UTC)

    for layer_name, module_path, fn_name in _LAYER_CONFIGS:
        try:
            mod = importlib.import_module(module_path)
            fn = getattr(mod, fn_name)
            report = await fn(db, org_id, window_days)
            score_field = _SCORE_FIELD_MAP.get(layer_name, "score")
            score = float(getattr(report, score_field, 0))

            # Check for duplicate (same org, layer, same day)
            existing = await db.execute(
                select(LayerScoreSnapshot).where(
                    LayerScoreSnapshot.organization_id == org_id,
                    LayerScoreSnapshot.layer_name == layer_name,
                    LayerScoreSnapshot.snapshot_date >= now.replace(hour=0, minute=0, second=0),
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            snap = LayerScoreSnapshot(
                organization_id=org_id,
                layer_name=layer_name,
                score=score,
                window_days=window_days,
                snapshot_date=now,
            )
            db.add(snap)
            written += 1
        except Exception:
            logger.warning("layer_snapshot: %s failed org=%d", layer_name, org_id, exc_info=True)
            errors += 1

    if written > 0:
        await db.commit()

    return {"written": written, "skipped": skipped, "errors": errors}


async def get_layer_trend(
    db: AsyncSession,
    org_id: int,
    layer_name: str,
    limit: int = 12,
) -> list[dict]:
    """Get historical score trend for a specific layer."""
    result = await db.execute(
        select(LayerScoreSnapshot).where(
            LayerScoreSnapshot.organization_id == org_id,
            LayerScoreSnapshot.layer_name == layer_name,
        ).order_by(LayerScoreSnapshot.snapshot_date.desc()).limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()  # chronological order
    return [
        {
            "date": row.snapshot_date.isoformat(),
            "score": round(row.score, 2),
            "window_days": row.window_days,
        }
        for row in rows
    ]


async def get_all_layer_trends(
    db: AsyncSession,
    org_id: int,
    limit: int = 12,
) -> dict:
    """Get trends for all layers."""
    trends: dict[str, list[dict]] = {}
    for layer_name, _, _ in _LAYER_CONFIGS:
        trends[layer_name] = await get_layer_trend(db, org_id, layer_name, limit)
    return trends


async def cleanup_old_snapshots(
    db: AsyncSession,
    org_id: int,
    retention_days: int = 365,
) -> int:
    """Remove snapshots older than retention period."""
    from sqlalchemy import delete

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await db.execute(
        delete(LayerScoreSnapshot).where(
            LayerScoreSnapshot.organization_id == org_id,
            LayerScoreSnapshot.snapshot_date < cutoff,
        )
    )
    if result.rowcount:
        await db.commit()
    return result.rowcount
