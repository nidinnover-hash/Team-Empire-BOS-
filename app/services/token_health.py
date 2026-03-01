"""Token health check and rotation service for integrations."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.token_crypto import encrypt_config
from app.models.integration import Integration

logger = logging.getLogger(__name__)

# OAuth integrations that support refresh_token flow
_OAUTH_TYPES = {"gmail", "google_calendar", "google_analytics"}
# PAT/API-key integrations — tokens don't auto-expire but should be rotated periodically
_PAT_TYPES = {"clickup", "github", "slack", "notion", "stripe", "hubspot", "calendly", "digitalocean", "elevenlabs", "perplexity"}
# Default staleness threshold for PAT tokens (days)
_PAT_ROTATION_WARNING_DAYS = 90
_PAT_ROTATION_DUE_SOON_DAYS = 75


async def check_token_health(
    db: AsyncSession,
    organization_id: int,
) -> list[dict[str, object]]:
    """Check all integrations for token expiry/staleness. Returns a list of health entries."""
    rows = (
        await db.execute(
            select(Integration).where(
                Integration.organization_id == organization_id,
                Integration.status == "connected",
            )
        )
    ).scalars().all()

    now = datetime.now(UTC)
    results: list[dict[str, object]] = []

    for row in rows:
        config = row.config_json or {}
        entry: dict[str, object] = {
            "type": row.type,
            "status": "healthy",
            "token_type": "oauth" if row.type in _OAUTH_TYPES else "pat",
            "rotation_status": "current",
            "last_rotated_at": row.updated_at.isoformat() if row.updated_at else None,
            "days_since_update": None,
            "expires_in_hours": None,
            "recommendation": None,
        }

        # Check age since last update
        if row.updated_at:
            age_days = (now - row.updated_at).total_seconds() / 86400
            entry["days_since_update"] = round(age_days, 1)

        if row.type in _OAUTH_TYPES:
            # Check token expiry for OAuth
            expires_at_str = config.get("expires_at")
            if expires_at_str:
                try:
                    if isinstance(expires_at_str, str):
                        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    elif isinstance(expires_at_str, int | float):
                        expires_at = datetime.fromtimestamp(expires_at_str, tz=UTC)
                    else:
                        expires_at = None

                    if expires_at:
                        hours_left = (expires_at - now).total_seconds() / 3600
                        entry["expires_in_hours"] = round(hours_left, 1)
                        if hours_left < 0:
                            entry["status"] = "expired"
                            entry["rotation_status"] = "overdue"
                            entry["recommendation"] = "Token expired. Re-authenticate via OAuth."
                        elif hours_left < 1:
                            entry["status"] = "expiring_soon"
                            entry["rotation_status"] = "due_soon"
                            entry["recommendation"] = "Token expires within 1 hour. Refresh recommended."
                        elif hours_left < 24:
                            entry["status"] = "warning"
                            entry["rotation_status"] = "due_soon"
                            entry["recommendation"] = "Token expires within 24 hours."
                except (ValueError, TypeError, OSError):
                    pass

            # Check if refresh_token exists
            if not config.get("refresh_token"):
                if entry["status"] == "healthy":
                    entry["status"] = "warning"
                entry["rotation_status"] = "manual_required"
                entry["recommendation"] = "No refresh_token available. Re-authenticate via OAuth to enable auto-refresh."

        elif row.type in _PAT_TYPES:
            # PAT tokens don't expire but should be rotated periodically
            age_days = entry.get("days_since_update")  # type: ignore[assignment]
            if isinstance(age_days, int | float) and age_days > _PAT_ROTATION_WARNING_DAYS:
                entry["status"] = "stale"
                entry["rotation_status"] = "overdue"
                entry["recommendation"] = f"Token is {int(age_days)} days old. Consider rotating for security."
            elif isinstance(age_days, int | float) and age_days > _PAT_ROTATION_DUE_SOON_DAYS:
                if entry["status"] == "healthy":
                    entry["status"] = "warning"
                entry["rotation_status"] = "due_soon"
                entry["recommendation"] = f"Token is {int(age_days)} days old. Schedule rotation this week."

        if entry["status"] == "healthy":
            entry["recommendation"] = "Token is healthy."

        results.append(entry)

    return results


async def rotate_oauth_token(
    db: AsyncSession,
    organization_id: int,
    integration_type: str,
) -> dict[str, object]:
    """Attempt to refresh an OAuth token proactively. Returns result dict."""
    row = (
        await db.execute(
            select(Integration).where(
                Integration.organization_id == organization_id,
                Integration.type == integration_type,
                Integration.status == "connected",
            )
        )
    ).scalar_one_or_none()

    if not row:
        return {"ok": False, "error": f"No connected {integration_type} integration found."}

    if integration_type not in _OAUTH_TYPES:
        return {"ok": False, "error": f"{integration_type} is not an OAuth integration. Rotate manually by reconnecting."}

    config = row.config_json or {}
    from app.core.token_crypto import decrypt_config
    decrypted = decrypt_config(config)
    refresh_token = decrypted.get("refresh_token")

    if not refresh_token:
        return {"ok": False, "error": "No refresh_token available. Re-authenticate via OAuth."}

    # Attempt refresh based on integration type
    try:
        if integration_type in ("gmail", "google_calendar", "google_analytics"):
            from app.tools.gmail import refresh_access_token
            new_tokens = refresh_access_token(refresh_token)
            if not new_tokens or not new_tokens.get("access_token"):
                return {"ok": False, "error": "Token refresh returned empty result."}

            # Update integration config with new tokens
            updated_config = {**decrypted, **new_tokens}
            row.config_json = encrypt_config(updated_config)
            row.updated_at = datetime.now(UTC)
            await db.commit()

            return {
                "ok": True,
                "type": integration_type,
                "refreshed_at": datetime.now(UTC).isoformat(),
                "expires_in": new_tokens.get("expires_in"),
            }
        else:
            return {"ok": False, "error": f"Refresh not implemented for {integration_type}."}

    except Exception as exc:
        logger.warning("Token rotation failed for %s: %s", integration_type, type(exc).__name__)
        return {"ok": False, "error": "Token rotation failed. Check integration configuration."}


async def get_rotation_report(
    db: AsyncSession,
    organization_id: int,
) -> dict[str, object]:
    """Get a full token health report across all integrations."""
    items = await check_token_health(db, organization_id)
    healthy = sum(1 for i in items if i["status"] == "healthy")
    warnings = sum(1 for i in items if i["status"] in ("warning", "stale", "expiring_soon"))
    critical = sum(1 for i in items if i["status"] == "expired")
    rotation_overdue = sum(1 for i in items if i.get("rotation_status") == "overdue")
    rotation_due_soon = sum(1 for i in items if i.get("rotation_status") == "due_soon")
    manual_required = sum(1 for i in items if i.get("rotation_status") == "manual_required")
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_integrations": len(items),
        "healthy": healthy,
        "warnings": warnings,
        "critical": critical,
        "rotation_overdue": rotation_overdue,
        "rotation_due_soon": rotation_due_soon,
        "manual_required": manual_required,
        "items": items,
    }


async def get_security_center(
    db: AsyncSession,
    organization_id: int,
) -> dict[str, object]:
    """Security center snapshot focused on token hygiene and rotation readiness."""
    def _to_int(value: object) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return 0
        return 0

    report = await get_rotation_report(db, organization_id)
    critical_count = _to_int(report.get("critical"))
    warning_count = _to_int(report.get("warnings"))
    overdue_count = _to_int(report.get("rotation_overdue"))
    due_soon_count = _to_int(report.get("rotation_due_soon"))
    manual_required = _to_int(report.get("manual_required"))
    total_integrations = _to_int(report.get("total_integrations"))
    healthy = _to_int(report.get("healthy"))

    level = "low"
    if critical_count > 0 or overdue_count > 0:
        level = "high"
    elif warning_count > 0 or due_soon_count > 0:
        level = "medium"

    next_actions: list[str] = []
    if critical_count > 0:
        next_actions.append("Reconnect expired OAuth integrations immediately.")
    if overdue_count > 0:
        next_actions.append("Rotate overdue PAT/API tokens in priority order.")
    if manual_required > 0:
        next_actions.append("Re-authenticate OAuth integrations missing refresh_token.")
    if not next_actions:
        next_actions.append("No urgent token actions required.")

    return {
        "generated_at": report.get("generated_at"),
        "risk_level": level,
        "summary": {
            "total_integrations": total_integrations,
            "healthy": healthy,
            "warnings": warning_count,
            "critical": critical_count,
            "rotation_overdue": overdue_count,
            "rotation_due_soon": due_soon_count,
            "manual_required": manual_required,
        },
        "next_actions": next_actions,
        "items": report.get("items", []),
    }
