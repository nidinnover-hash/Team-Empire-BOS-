from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.services import organization as org_service
from app.services.org_readiness import build_org_readiness_report

AutonomyMode = Literal["suggest_only", "approved_execution", "autonomous"]
_MODE_RANK: dict[AutonomyMode, int] = {
    "suggest_only": 0,
    "approved_execution": 1,
    "autonomous": 2,
}


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


def default_autonomy_policy() -> AutonomyPolicy:
    # Backward-compatible defaults: no behavior break for current deployments.
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


def _normalize_mode(value: object) -> AutonomyMode:
    mode = str(value or "").strip().lower()
    if mode in _MODE_RANK:
        return mode  # type: ignore[return-value]
    return "approved_execution"


def _to_int(value: object, fallback: int, *, min_value: int = 0, max_value: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
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
    try:
        user_id = int(user_id_raw) if user_id_raw is not None else None
    except (TypeError, ValueError):
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


def _normalize_history_item(raw: dict[str, object]) -> AutonomyPolicyHistoryItem | None:
    version_id_raw = raw.get("version_id")
    version_id = str(version_id_raw).strip() if version_id_raw is not None else ""
    if not version_id:
        return None
    policy_raw = raw.get("policy")
    if not isinstance(policy_raw, dict):
        return None
    item: AutonomyPolicyHistoryItem = {
        "version_id": version_id,
        "updated_at": _normalize_meta({"updated_at": raw.get("updated_at")}).get("updated_at"),
        "updated_by_user_id": _normalize_meta({"updated_by_user_id": raw.get("updated_by_user_id")}).get("updated_by_user_id"),
        "updated_by_email": _normalize_meta({"updated_by_email": raw.get("updated_by_email")}).get("updated_by_email"),
        "rollback_of_version_id": str(raw.get("rollback_of_version_id")).strip()
        if raw.get("rollback_of_version_id") is not None
        else None,
        "policy": _normalize_policy(policy_raw),
    }
    if not item["rollback_of_version_id"]:
        item["rollback_of_version_id"] = None
    return item


async def get_autonomy_policy(db: AsyncSession, organization_id: int) -> AutonomyPolicy:
    policy_config = await org_service.get_policy_config(db, organization_id)
    raw = policy_config.get("autonomy_policy", {})
    if not isinstance(raw, dict):
        raw = {}
    return _normalize_policy(raw)


async def get_autonomy_policy_meta(db: AsyncSession, organization_id: int) -> AutonomyPolicyMeta:
    policy_config = await org_service.get_policy_config(db, organization_id)
    raw = policy_config.get("autonomy_policy_meta", {})
    if not isinstance(raw, dict):
        raw = {}
    return _normalize_meta(raw)


async def get_autonomy_policy_history(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 20,
) -> list[AutonomyPolicyHistoryItem]:
    policy_config = await org_service.get_policy_config(db, organization_id)
    raw = policy_config.get("autonomy_policy_history", [])
    if not isinstance(raw, list):
        raw = []
    items: list[AutonomyPolicyHistoryItem] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        normalized = _normalize_history_item(row)
        if normalized is not None:
            items.append(normalized)
        if len(items) >= max(1, int(limit)):
            break
    return items


async def update_autonomy_policy(
    db: AsyncSession,
    *,
    organization_id: int,
    updates: dict[str, object],
    updated_by_user_id: int | None = None,
    updated_by_email: str | None = None,
) -> tuple[AutonomyPolicy, AutonomyPolicyMeta] | None:
    current = await get_autonomy_policy(db, organization_id)
    merged = dict(current)
    for key, value in updates.items():
        merged[key] = value
    normalized = _normalize_policy(merged)
    meta: AutonomyPolicyMeta = {
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by_user_id": updated_by_user_id,
        "updated_by_email": updated_by_email,
    }
    actor_user_id = meta["updated_by_user_id"]
    actor_email = meta["updated_by_email"]
    if not isinstance(actor_user_id, int):
        meta["updated_by_user_id"] = None
    if not isinstance(actor_email, str):
        meta["updated_by_email"] = None
    else:
        cleaned_email = actor_email.strip().lower()
        meta["updated_by_email"] = cleaned_email or None
    existing_history = await get_autonomy_policy_history(db, organization_id, limit=50)
    version_id = meta["updated_at"] or datetime.now(UTC).isoformat()
    new_item: AutonomyPolicyHistoryItem = {
        "version_id": version_id,
        "updated_at": meta["updated_at"],
        "updated_by_user_id": meta["updated_by_user_id"],
        "updated_by_email": meta["updated_by_email"],
        "rollback_of_version_id": None,
        "policy": normalized,
    }
    merged_history = [new_item, *existing_history]
    out = await org_service.update_policy_config(
        db,
        organization_id,
        {
            "autonomy_policy": normalized,
            "autonomy_policy_meta": meta,
            "autonomy_policy_history": merged_history[:50],
        },
    )
    if out is None:
        return None
    return normalized, meta


async def rollback_autonomy_policy(
    db: AsyncSession,
    *,
    organization_id: int,
    version_id: str,
    updated_by_user_id: int | None = None,
    updated_by_email: str | None = None,
) -> tuple[AutonomyPolicy, AutonomyPolicyMeta] | None:
    history = await get_autonomy_policy_history(db, organization_id, limit=50)
    target = next((item for item in history if item.get("version_id") == version_id), None)
    if target is None:
        return None
    target_policy = target.get("policy")
    if not isinstance(target_policy, dict):
        return None
    normalized = _normalize_policy(target_policy)
    meta: AutonomyPolicyMeta = {
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by_user_id": updated_by_user_id,
        "updated_by_email": (updated_by_email or "").strip().lower() or None,
    }
    if not isinstance(meta["updated_by_user_id"], int):
        meta["updated_by_user_id"] = None
    version_id_new = meta["updated_at"] or datetime.now(UTC).isoformat()
    new_item: AutonomyPolicyHistoryItem = {
        "version_id": version_id_new,
        "updated_at": meta["updated_at"],
        "updated_by_user_id": meta["updated_by_user_id"],
        "updated_by_email": meta["updated_by_email"],
        "rollback_of_version_id": version_id,
        "policy": normalized,
    }
    out = await org_service.update_policy_config(
        db,
        organization_id,
        {
            "autonomy_policy": normalized,
            "autonomy_policy_meta": meta,
            "autonomy_policy_history": [new_item] + history[:49],
        },
    )
    if out is None:
        return None
    return normalized, meta


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
    evaluation = await evaluate_autonomy_modes(db, org=org)
    if "approved_execution" in evaluation["allowed_modes"] or "autonomous" in evaluation["allowed_modes"]:
        return True, ""
    reason = evaluation["reasons"][0] if evaluation["reasons"] else "Execution denied by autonomy policy."
    return False, reason
