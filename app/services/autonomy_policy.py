from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.autonomy_policy import AutonomyPolicyConfig, AutonomyPolicyVersion
from app.models.execution import Execution
from app.models.organization import Organization
from app.services import organization as org_service
from app.services.org_readiness import build_org_readiness_report

AutonomyMode = Literal["suggest_only", "approved_execution", "autonomous"]
_MODE_RANK: dict[AutonomyMode, int] = {
    "suggest_only": 0,
    "approved_execution": 1,
    "autonomous": 2,
}
_MAX_ROLLOUT_ACTIONS_PER_DAY = 10_000
_DEFAULT_MAX_ACTIONS_PER_DAY = 250


class AutonomyPolicy(TypedDict):
    current_mode: AutonomyMode
    allow_auto_approval: bool
    min_readiness_for_auto_approval: int
    min_readiness_for_approved_execution: int
    min_readiness_for_autonomous: int
    block_on_unread_high_alerts: bool
    block_on_stale_integrations: bool
    block_on_sla_breaches: bool


class AutonomyEvaluation(TypedDict):
    allowed_modes: list[AutonomyMode]
    denied_modes: list[Literal["approved_execution", "autonomous"]]
    reasons: list[str]


class AutonomyPolicyMeta(TypedDict, total=False):
    updated_at: str | None
    updated_by_user_id: int | None
    updated_by_email: str | None


class AutonomyPolicyHistoryItem(TypedDict, total=False):
    version_id: str
    updated_at: str | None
    updated_by_user_id: int | None
    updated_by_email: str | None
    rollback_of_version_id: str | None
    policy: AutonomyPolicy


class AutonomyRollout(TypedDict):
    kill_switch: bool
    pilot_org_ids: list[int]
    max_actions_per_day: int


class RolloutDecision(TypedDict):
    allowed: bool
    reason: str
    actions_today: int
    max_actions_per_day: int


_TEMPLATES: dict[str, tuple[str, str, AutonomyPolicy]] = {
    "conservative": (
        "Conservative",
        "Human-first mode with strict readiness and lower automation risk.",
        {
            "current_mode": "suggest_only",
            "allow_auto_approval": False,
            "min_readiness_for_auto_approval": 90,
            "min_readiness_for_approved_execution": 85,
            "min_readiness_for_autonomous": 98,
            "block_on_unread_high_alerts": True,
            "block_on_stale_integrations": True,
            "block_on_sla_breaches": True,
        },
    ),
    "balanced": (
        "Balanced",
        "Default operating profile with approvals and controlled automation.",
        {
            "current_mode": "approved_execution",
            "allow_auto_approval": True,
            "min_readiness_for_auto_approval": 70,
            "min_readiness_for_approved_execution": 65,
            "min_readiness_for_autonomous": 90,
            "block_on_unread_high_alerts": True,
            "block_on_stale_integrations": True,
            "block_on_sla_breaches": True,
        },
    ),
    "aggressive": (
        "Aggressive",
        "High automation profile for mature orgs with resilient operations.",
        {
            "current_mode": "autonomous",
            "allow_auto_approval": True,
            "min_readiness_for_auto_approval": 55,
            "min_readiness_for_approved_execution": 50,
            "min_readiness_for_autonomous": 75,
            "block_on_unread_high_alerts": True,
            "block_on_stale_integrations": False,
            "block_on_sla_breaches": True,
        },
    ),
}


def default_autonomy_policy() -> AutonomyPolicy:
    return {
        "current_mode": "approved_execution",
        "allow_auto_approval": True,
        "min_readiness_for_auto_approval": 70,
        "min_readiness_for_approved_execution": 65,
        "min_readiness_for_autonomous": 90,
        "block_on_unread_high_alerts": True,
        "block_on_stale_integrations": True,
        "block_on_sla_breaches": True,
    }


def default_rollout_config() -> AutonomyRollout:
    return {
        "kill_switch": False,
        "pilot_org_ids": [],
        "max_actions_per_day": _DEFAULT_MAX_ACTIONS_PER_DAY,
    }


def list_policy_templates() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for template_id, (label, description, policy) in _TEMPLATES.items():
        out.append(
            {
                "id": template_id,
                "label": label,
                "description": description,
                "policy": dict(policy),
            }
        )
    return out


def get_policy_template(template_id: str) -> dict[str, object] | None:
    key = str(template_id or "").strip().lower()
    row = _TEMPLATES.get(key)
    if row is None:
        return None
    label, description, policy = row
    return {"id": key, "label": label, "description": description, "policy": dict(policy)}


def _normalize_mode(value: object) -> AutonomyMode:
    mode = str(value or "").strip().lower()
    if mode in _MODE_RANK:
        return mode  # type: ignore[return-value]
    return "approved_execution"


def _to_int(value: object, fallback: int, *, min_value: int = 0, max_value: int = 100) -> int:
    parsed: int | None = None
    if isinstance(value, bool):
        parsed = int(value)
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        parsed = int(value)
    elif isinstance(value, str | bytes | bytearray):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = None
    if parsed is None:
        parsed = fallback
    return max(min_value, min(max_value, parsed))


def _normalize_policy(raw: dict[str, object]) -> AutonomyPolicy:
    defaults = default_autonomy_policy()
    return {
        "current_mode": _normalize_mode(raw.get("current_mode", defaults["current_mode"])),
        "allow_auto_approval": bool(raw.get("allow_auto_approval", defaults["allow_auto_approval"])),
        "min_readiness_for_auto_approval": _to_int(
            raw.get("min_readiness_for_auto_approval"),
            defaults["min_readiness_for_auto_approval"],
        ),
        "min_readiness_for_approved_execution": _to_int(
            raw.get("min_readiness_for_approved_execution"),
            defaults["min_readiness_for_approved_execution"],
        ),
        "min_readiness_for_autonomous": _to_int(
            raw.get("min_readiness_for_autonomous"),
            defaults["min_readiness_for_autonomous"],
        ),
        "block_on_unread_high_alerts": bool(
            raw.get("block_on_unread_high_alerts", defaults["block_on_unread_high_alerts"])
        ),
        "block_on_stale_integrations": bool(
            raw.get("block_on_stale_integrations", defaults["block_on_stale_integrations"])
        ),
        "block_on_sla_breaches": bool(raw.get("block_on_sla_breaches", defaults["block_on_sla_breaches"])),
    }


def _normalize_meta(raw: dict[str, object]) -> AutonomyPolicyMeta:
    updated_at_raw = raw.get("updated_at")
    updated_at = str(updated_at_raw).strip() if updated_at_raw is not None else None
    if not updated_at:
        updated_at = None
    user_id_raw = raw.get("updated_by_user_id")
    if isinstance(user_id_raw, bool):
        user_id = int(user_id_raw)
    elif isinstance(user_id_raw, int):
        user_id = user_id_raw
    elif isinstance(user_id_raw, float):
        user_id = int(user_id_raw)
    elif isinstance(user_id_raw, str | bytes | bytearray):
        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError):
            user_id = None
    else:
        user_id = None
    email_raw = raw.get("updated_by_email")
    email = str(email_raw).strip().lower() if email_raw is not None else None
    if not email:
        email = None
    return {
        "updated_at": updated_at,
        "updated_by_user_id": user_id,
        "updated_by_email": email,
    }


def _normalize_rollout(raw: dict[str, object]) -> AutonomyRollout:
    defaults = default_rollout_config()
    pilot_raw = raw.get("pilot_org_ids", defaults["pilot_org_ids"])
    pilot_ids: list[int] = []
    if isinstance(pilot_raw, list):
        for value in pilot_raw:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0 and parsed not in pilot_ids:
                pilot_ids.append(parsed)
    return {
        "kill_switch": bool(raw.get("kill_switch", defaults["kill_switch"])),
        "pilot_org_ids": pilot_ids,
        "max_actions_per_day": _to_int(
            raw.get("max_actions_per_day"),
            defaults["max_actions_per_day"],
            min_value=1,
            max_value=_MAX_ROLLOUT_ACTIONS_PER_DAY,
        ),
    }


def _normalize_history_item(raw: dict[str, object]) -> AutonomyPolicyHistoryItem | None:
    version_id = str(raw.get("version_id") or "").strip()
    policy_raw = raw.get("policy")
    if not version_id or not isinstance(policy_raw, dict):
        return None
    meta = _normalize_meta(raw)
    rollback_of = str(raw.get("rollback_of_version_id") or "").strip() or None
    return {
        "version_id": version_id,
        "updated_at": meta.get("updated_at"),
        "updated_by_user_id": meta.get("updated_by_user_id"),
        "updated_by_email": meta.get("updated_by_email"),
        "rollback_of_version_id": rollback_of,
        "policy": _normalize_policy(policy_raw),
    }


def _record_to_policy(record: AutonomyPolicyConfig) -> AutonomyPolicy:
    return _normalize_policy(
        {
            "current_mode": record.current_mode,
            "allow_auto_approval": record.allow_auto_approval,
            "min_readiness_for_auto_approval": record.min_readiness_for_auto_approval,
            "min_readiness_for_approved_execution": record.min_readiness_for_approved_execution,
            "min_readiness_for_autonomous": record.min_readiness_for_autonomous,
            "block_on_unread_high_alerts": record.block_on_unread_high_alerts,
            "block_on_stale_integrations": record.block_on_stale_integrations,
            "block_on_sla_breaches": record.block_on_sla_breaches,
        }
    )


def _record_to_rollout(record: AutonomyPolicyConfig) -> AutonomyRollout:
    return _normalize_rollout(
        {
            "kill_switch": record.kill_switch,
            "pilot_org_ids": record.pilot_org_ids_json or [],
            "max_actions_per_day": record.max_actions_per_day,
        }
    )


def _record_to_meta(record: AutonomyPolicyConfig) -> AutonomyPolicyMeta:
    return {
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "updated_by_user_id": int(record.updated_by_user_id) if record.updated_by_user_id is not None else None,
        "updated_by_email": (record.updated_by_email or "").strip().lower() or None,
    }


async def _get_config_record(db: AsyncSession, organization_id: int) -> AutonomyPolicyConfig | None:
    return (
        await db.execute(
            select(AutonomyPolicyConfig).where(AutonomyPolicyConfig.organization_id == organization_id)
        )
    ).scalar_one_or_none()


async def _legacy_values(
    db: AsyncSession, organization_id: int
) -> tuple[AutonomyPolicy, AutonomyRollout, AutonomyPolicyMeta, list[AutonomyPolicyHistoryItem]]:
    policy_config = await org_service.get_policy_config(db, organization_id)
    policy_raw = policy_config.get("autonomy_policy", {})
    if not isinstance(policy_raw, dict):
        policy_raw = {}
    rollout_raw = policy_config.get("autonomy_rollout", {})
    if not isinstance(rollout_raw, dict):
        rollout_raw = {}
    meta_raw = policy_config.get("autonomy_policy_meta", {})
    if not isinstance(meta_raw, dict):
        meta_raw = {}
    history_raw = policy_config.get("autonomy_policy_history", [])
    if not isinstance(history_raw, list):
        history_raw = []
    history: list[AutonomyPolicyHistoryItem] = []
    for row in history_raw:
        if not isinstance(row, dict):
            continue
        item = _normalize_history_item(row)
        if item is not None:
            history.append(item)
    return _normalize_policy(policy_raw), _normalize_rollout(rollout_raw), _normalize_meta(meta_raw), history


async def _upsert_config_record(
    db: AsyncSession,
    *,
    organization_id: int,
    policy: AutonomyPolicy,
    rollout: AutonomyRollout,
    meta: AutonomyPolicyMeta,
) -> AutonomyPolicyConfig:
    record = await _get_config_record(db, organization_id)
    if record is None:
        record = AutonomyPolicyConfig(organization_id=organization_id)
        db.add(record)
    record.current_mode = policy["current_mode"]
    record.allow_auto_approval = bool(policy["allow_auto_approval"])
    record.min_readiness_for_auto_approval = int(policy["min_readiness_for_auto_approval"])
    record.min_readiness_for_approved_execution = int(policy["min_readiness_for_approved_execution"])
    record.min_readiness_for_autonomous = int(policy["min_readiness_for_autonomous"])
    record.block_on_unread_high_alerts = bool(policy["block_on_unread_high_alerts"])
    record.block_on_stale_integrations = bool(policy["block_on_stale_integrations"])
    record.block_on_sla_breaches = bool(policy["block_on_sla_breaches"])
    record.kill_switch = bool(rollout["kill_switch"])
    record.pilot_org_ids_json = list(rollout["pilot_org_ids"])
    record.max_actions_per_day = int(rollout["max_actions_per_day"])
    record.updated_at = datetime.now(UTC)
    record.updated_by_user_id = meta.get("updated_by_user_id")
    record.updated_by_email = meta.get("updated_by_email")
    await db.flush()
    return record


def _serialize_history(items: list[AutonomyPolicyHistoryItem]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for item in items:
        out.append(
            {
                "version_id": item.get("version_id"),
                "updated_at": item.get("updated_at"),
                "updated_by_user_id": item.get("updated_by_user_id"),
                "updated_by_email": item.get("updated_by_email"),
                "rollback_of_version_id": item.get("rollback_of_version_id"),
                "policy": item.get("policy", {}),
            }
        )
    return out


async def _sync_legacy_policy_json(
    db: AsyncSession,
    *,
    organization_id: int,
    policy: AutonomyPolicy,
    rollout: AutonomyRollout,
    meta: AutonomyPolicyMeta,
    history: list[AutonomyPolicyHistoryItem],
) -> None:
    await org_service.update_policy_config(
        db,
        organization_id,
        {
            "autonomy_policy": dict(policy),
            "autonomy_rollout": dict(rollout),
            "autonomy_policy_meta": dict(meta),
            "autonomy_policy_history": _serialize_history(history[:50]),
        },
    )


async def get_autonomy_policy(db: AsyncSession, organization_id: int) -> AutonomyPolicy:
    record = await _get_config_record(db, organization_id)
    if record is not None:
        return _record_to_policy(record)
    policy, _rollout, _meta, _history = await _legacy_values(db, organization_id)
    return policy


async def get_autonomy_policy_meta(db: AsyncSession, organization_id: int) -> AutonomyPolicyMeta:
    record = await _get_config_record(db, organization_id)
    if record is not None:
        return _record_to_meta(record)
    _policy, _rollout, meta, _history = await _legacy_values(db, organization_id)
    return meta


async def get_rollout_config(db: AsyncSession, organization_id: int) -> AutonomyRollout:
    record = await _get_config_record(db, organization_id)
    if record is not None:
        return _record_to_rollout(record)
    _policy, rollout, _meta, _history = await _legacy_values(db, organization_id)
    return rollout


async def get_autonomy_policy_history(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 20,
) -> list[AutonomyPolicyHistoryItem]:
    rows = (
        await db.execute(
            select(AutonomyPolicyVersion)
            .where(AutonomyPolicyVersion.organization_id == organization_id)
            .order_by(AutonomyPolicyVersion.updated_at.desc(), AutonomyPolicyVersion.id.desc())
            .limit(max(1, int(limit)))
        )
    ).scalars().all()
    if rows:
        items: list[AutonomyPolicyHistoryItem] = []
        for row in rows:
            items.append(
                {
                    "version_id": row.version_id,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "updated_by_user_id": int(row.updated_by_user_id) if row.updated_by_user_id is not None else None,
                    "updated_by_email": (row.updated_by_email or "").strip().lower() or None,
                    "rollback_of_version_id": row.rollback_of_version_id,
                    "policy": _normalize_policy(row.policy_json if isinstance(row.policy_json, dict) else {}),
                }
            )
        return items
    _policy, _rollout, _meta, history = await _legacy_values(db, organization_id)
    return history[: max(1, int(limit))]


def _new_version_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


async def update_autonomy_policy(
    db: AsyncSession,
    *,
    organization_id: int,
    updates: dict[str, object],
    updated_by_user_id: int | None = None,
    updated_by_email: str | None = None,
) -> tuple[AutonomyPolicy, AutonomyPolicyMeta] | None:
    current_policy = await get_autonomy_policy(db, organization_id)
    current_rollout = await get_rollout_config(db, organization_id)
    merged = dict(current_policy)
    merged.update(updates)
    policy = _normalize_policy(merged)
    meta: AutonomyPolicyMeta = _normalize_meta(
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by_user_id": updated_by_user_id,
            "updated_by_email": updated_by_email,
        }
    )
    await _upsert_config_record(
        db,
        organization_id=organization_id,
        policy=policy,
        rollout=current_rollout,
        meta=meta,
    )
    version_id = _new_version_id()
    db.add(
        AutonomyPolicyVersion(
            organization_id=organization_id,
            version_id=version_id,
            policy_json=dict(policy),
            rollback_of_version_id=None,
            updated_at=datetime.now(UTC),
            updated_by_user_id=meta.get("updated_by_user_id"),
            updated_by_email=meta.get("updated_by_email"),
        )
    )
    await db.commit()
    history = await get_autonomy_policy_history(db, organization_id, limit=50)
    await _sync_legacy_policy_json(
        db,
        organization_id=organization_id,
        policy=policy,
        rollout=current_rollout,
        meta=meta,
        history=history,
    )
    return policy, meta


async def update_rollout_config(
    db: AsyncSession,
    *,
    organization_id: int,
    updates: dict[str, object],
) -> AutonomyRollout | None:
    current_policy = await get_autonomy_policy(db, organization_id)
    current_rollout = await get_rollout_config(db, organization_id)
    merged = dict(current_rollout)
    merged.update(updates)
    rollout = _normalize_rollout(merged)
    meta = await get_autonomy_policy_meta(db, organization_id)
    await _upsert_config_record(
        db,
        organization_id=organization_id,
        policy=current_policy,
        rollout=rollout,
        meta=meta,
    )
    await db.commit()
    history = await get_autonomy_policy_history(db, organization_id, limit=50)
    await _sync_legacy_policy_json(
        db,
        organization_id=organization_id,
        policy=current_policy,
        rollout=rollout,
        meta=meta,
        history=history,
    )
    return rollout


async def rollback_autonomy_policy(
    db: AsyncSession,
    *,
    organization_id: int,
    version_id: str,
    updated_by_user_id: int | None = None,
    updated_by_email: str | None = None,
) -> tuple[AutonomyPolicy, AutonomyPolicyMeta] | None:
    target = (
        await db.execute(
            select(AutonomyPolicyVersion).where(
                AutonomyPolicyVersion.organization_id == organization_id,
                AutonomyPolicyVersion.version_id == version_id,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        return None
    target_policy = _normalize_policy(target.policy_json if isinstance(target.policy_json, dict) else {})
    current_rollout = await get_rollout_config(db, organization_id)
    meta: AutonomyPolicyMeta = _normalize_meta(
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by_user_id": updated_by_user_id,
            "updated_by_email": updated_by_email,
        }
    )
    await _upsert_config_record(
        db,
        organization_id=organization_id,
        policy=target_policy,
        rollout=current_rollout,
        meta=meta,
    )
    db.add(
        AutonomyPolicyVersion(
            organization_id=organization_id,
            version_id=_new_version_id(),
            policy_json=dict(target_policy),
            rollback_of_version_id=version_id,
            updated_at=datetime.now(UTC),
            updated_by_user_id=meta.get("updated_by_user_id"),
            updated_by_email=meta.get("updated_by_email"),
        )
    )
    await db.commit()
    history = await get_autonomy_policy_history(db, organization_id, limit=50)
    await _sync_legacy_policy_json(
        db,
        organization_id=organization_id,
        policy=target_policy,
        rollout=current_rollout,
        meta=meta,
        history=history,
    )
    return target_policy, meta


async def evaluate_rollout_for_execution(
    db: AsyncSession,
    *,
    org: Organization,
) -> RolloutDecision:
    rollout = await get_rollout_config(db, int(org.id))
    if bool(rollout["kill_switch"]):
        return {
            "allowed": False,
            "reason": "Global execution kill switch is enabled for this organization.",
            "actions_today": 0,
            "max_actions_per_day": int(rollout["max_actions_per_day"]),
        }
    pilot_ids = rollout["pilot_org_ids"]
    if pilot_ids and int(org.id) not in pilot_ids:
        return {
            "allowed": False,
            "reason": "Organization is outside current autonomy pilot scope.",
            "actions_today": 0,
            "max_actions_per_day": int(rollout["max_actions_per_day"]),
        }
    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    actions_today = int(
        (
            await db.execute(
                select(func.count(Execution.id)).where(
                    Execution.organization_id == int(org.id),
                    Execution.started_at >= start_of_day,
                )
            )
        ).scalar_one()
        or 0
    )
    max_actions = int(rollout["max_actions_per_day"])
    if actions_today >= max_actions:
        return {
            "allowed": False,
            "reason": "Daily execution cap reached for this organization.",
            "actions_today": actions_today,
            "max_actions_per_day": max_actions,
        }
    return {
        "allowed": True,
        "reason": "",
        "actions_today": actions_today,
        "max_actions_per_day": max_actions,
    }


async def evaluate_rollout_for_auto_approval(
    db: AsyncSession,
    *,
    org: Organization,
) -> RolloutDecision:
    rollout = await get_rollout_config(db, int(org.id))
    if bool(rollout["kill_switch"]):
        return {
            "allowed": False,
            "reason": "Global execution kill switch is enabled for this organization.",
            "actions_today": 0,
            "max_actions_per_day": int(rollout["max_actions_per_day"]),
        }
    pilot_ids = rollout["pilot_org_ids"]
    if pilot_ids and int(org.id) not in pilot_ids:
        return {
            "allowed": False,
            "reason": "Organization is outside current autonomy pilot scope.",
            "actions_today": 0,
            "max_actions_per_day": int(rollout["max_actions_per_day"]),
        }
    return {
        "allowed": True,
        "reason": "",
        "actions_today": 0,
        "max_actions_per_day": int(rollout["max_actions_per_day"]),
    }


async def evaluate_autonomy_modes(
    db: AsyncSession,
    *,
    org: Organization,
) -> AutonomyEvaluation:
    policy = await get_autonomy_policy(db, int(org.id))
    readiness = await build_org_readiness_report(db, org)
    metric_map = {metric.name: metric.value for metric in readiness.metrics}

    allowed: list[AutonomyMode] = ["suggest_only"]
    denied: list[Literal["approved_execution", "autonomous"]] = []
    reasons: list[str] = []

    mode_cap = _MODE_RANK[policy["current_mode"]]

    approved_ok = (
        readiness.status != "blocked"
        and readiness.score >= int(policy["min_readiness_for_approved_execution"])
    )
    if approved_ok and mode_cap >= _MODE_RANK["approved_execution"]:
        allowed.append("approved_execution")
    else:
        denied.append("approved_execution")
        if mode_cap < _MODE_RANK["approved_execution"]:
            reasons.append("Policy current_mode caps execution at suggest_only.")
        else:
            reasons.append("Approved execution denied by readiness threshold.")

    autonomous_ok = (
        readiness.status == "ready"
        and readiness.score >= int(policy["min_readiness_for_autonomous"])
    )
    if bool(policy["block_on_stale_integrations"]) and int(metric_map.get("stale_integrations", 0)) > 0:
        autonomous_ok = False
        reasons.append("Autonomous blocked: stale integrations detected.")
    if bool(policy["block_on_sla_breaches"]) and int(metric_map.get("pending_approvals_sla_breached", 0)) > 0:
        autonomous_ok = False
        reasons.append("Autonomous blocked: approval SLA breaches detected.")
    if bool(policy["block_on_unread_high_alerts"]) and int(metric_map.get("unread_high_alerts", 0)) > 0:
        autonomous_ok = False
        reasons.append("Autonomous blocked: unread high-severity alerts detected.")
    if autonomous_ok and mode_cap >= _MODE_RANK["autonomous"]:
        allowed.append("autonomous")
    else:
        denied.append("autonomous")
        if mode_cap < _MODE_RANK["autonomous"]:
            reasons.append("Policy current_mode caps execution below autonomous.")
        else:
            reasons.append("Autonomous denied by readiness/risk thresholds.")

    return {
        "allowed_modes": allowed,
        "denied_modes": denied,
        "reasons": reasons + readiness.blockers,
    }


async def can_auto_approve(
    db: AsyncSession,
    *,
    org: Organization,
) -> tuple[bool, str]:
    rollout = await evaluate_rollout_for_auto_approval(db, org=org)
    if not rollout["allowed"]:
        return False, rollout["reason"]
    policy = await get_autonomy_policy(db, int(org.id))
    if not bool(policy["allow_auto_approval"]):
        return False, "Auto-approval disabled by autonomy policy."
    readiness = await build_org_readiness_report(db, org)
    if readiness.score < int(policy["min_readiness_for_auto_approval"]):
        return False, "Auto-approval blocked by readiness threshold."
    metric_map = {metric.name: metric.value for metric in readiness.metrics}
    if bool(policy["block_on_stale_integrations"]) and int(metric_map.get("stale_integrations", 0)) > 0:
        return False, "Auto-approval blocked: stale integrations detected."
    if bool(policy["block_on_sla_breaches"]) and int(metric_map.get("pending_approvals_sla_breached", 0)) > 0:
        return False, "Auto-approval blocked: approval SLA breaches detected."
    if bool(policy["block_on_unread_high_alerts"]) and int(metric_map.get("unread_high_alerts", 0)) > 0:
        return False, "Auto-approval blocked: unread high-severity alerts detected."
    return True, ""


async def can_execute_post_approval(
    db: AsyncSession,
    *,
    org: Organization,
) -> tuple[bool, str]:
    rollout = await evaluate_rollout_for_execution(db, org=org)
    if not rollout["allowed"]:
        return False, rollout["reason"]
    policy = await get_autonomy_policy(db, int(org.id))
    mode_rank = _MODE_RANK.get(policy["current_mode"], 0)
    if mode_rank >= _MODE_RANK["approved_execution"]:
        return True, ""
    return False, "Execution denied by autonomy policy."
