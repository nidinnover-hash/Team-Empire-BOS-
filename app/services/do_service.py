from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import require_org_id
from app.models.ceo_control import (
    DigitalOceanCostSnapshot,
    DigitalOceanDropletSnapshot,
    DigitalOceanTeamSnapshot,
)
from app.services import integration as integration_service
from app.tools import digitalocean as do_tool

_TYPE = "digitalocean"


async def connect_digitalocean(db: AsyncSession, org_id: int, api_token: str) -> dict[str, Any]:
    require_org_id(org_id)
    account = await do_tool.get_account(api_token)
    item = await integration_service.connect_integration(
        db=db,
        organization_id=org_id,
        integration_type=_TYPE,
        config_json={
            "access_token": api_token,
            "account_email": account.get("email"),
            "connected_at": datetime.now(UTC).isoformat(),
        },
    )
    return {"id": item.id, "status": item.status, "email": account.get("email")}


async def get_digitalocean_status(db: AsyncSession, org_id: int) -> dict[str, Any]:
    item = await integration_service.get_integration_by_type(db, org_id, _TYPE)
    if item is None:
        return {"connected": False, "last_sync_at": None}
    return {
        "connected": item.status == "connected",
        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
    }


async def sync_digitalocean(db: AsyncSession, org_id: int) -> dict[str, Any]:
    item = await integration_service.get_integration_by_type(db, org_id, _TYPE)
    if item is None or item.status != "connected":
        return {"droplets": 0, "members": 0, "error": "DigitalOcean integration is not connected"}
    token = str((item.config_json or {}).get("access_token") or "")
    if not token:
        return {"droplets": 0, "members": 0, "error": "Missing access_token in DigitalOcean config"}

    now = datetime.now(UTC)
    try:
        droplets = await do_tool.list_droplets(token)
        members = await do_tool.list_team_members(token)
        balance = await do_tool.get_balance(token)
    except (httpx.HTTPError, RuntimeError, ValueError, TypeError, TimeoutError) as exc:
        return {"droplets": 0, "members": 0, "error": type(exc).__name__}

    await db.execute(delete(DigitalOceanDropletSnapshot).where(DigitalOceanDropletSnapshot.organization_id == org_id))
    await db.execute(delete(DigitalOceanTeamSnapshot).where(DigitalOceanTeamSnapshot.organization_id == org_id))

    for d in droplets:
        db.add(
            DigitalOceanDropletSnapshot(
                organization_id=org_id,
                droplet_id=str(d.get("id", "")),
                name=str(d.get("name", "droplet")),
                region=((d.get("region") or {}).get("slug") if isinstance(d.get("region"), dict) else None),
                size=((d.get("size") or {}).get("slug") if isinstance(d.get("size"), dict) else None),
                status=str(d.get("status") or ""),
                backups_enabled=bool(d.get("features") and "backups" in d.get("features", [])),
                synced_at=now,
            )
        )

    for m in members:
        db.add(
            DigitalOceanTeamSnapshot(
                organization_id=org_id,
                email=str(m.get("email", "")),
                role=str(m.get("role") or ""),
                synced_at=now,
            )
        )

    raw_amount = balance.get("month_to_date_balance")
    if raw_amount in (None, ""):
        amount = None
    else:
        try:
            amount = float(str(raw_amount))
        except (TypeError, ValueError):
            amount = None
    db.add(
        DigitalOceanCostSnapshot(
            organization_id=org_id,
            period_start=None,
            period_end=None,
            amount_usd=amount,
            currency="USD",
            synced_at=now,
        )
    )

    await db.commit()
    await integration_service.mark_sync_time(db, item)
    return {"droplets": len(droplets), "members": len(members), "error": None}
