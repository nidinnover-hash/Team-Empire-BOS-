from __future__ import annotations

import argparse
import asyncio
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.token_crypto import encrypt_token
from app.db.session import AsyncSessionLocal
from app.models.integration import Integration
from app.models.webhook import WebhookEndpoint


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Security rotation drill: validate rotation workflow and optionally rotate webhook secrets. "
            "Default mode is dry-run."
        )
    )
    parser.add_argument("--apply", action="store_true", help="Persist webhook secret rotation.")
    parser.add_argument(
        "--organization-id",
        type=int,
        default=None,
        help="Restrict drill to one organization.",
    )
    return parser.parse_args()


async def _count_integrations(org_id: int | None) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        q = select(
            func.count(Integration.id),
            func.count().filter(Integration.status == "connected"),
        )
        if org_id is not None:
            q = q.where(Integration.organization_id == org_id)
        row = (await db.execute(q)).one()
        return int(row[0] or 0), int(row[1] or 0)


async def _rotate_webhook_secrets(*, apply: bool, org_id: int | None) -> int:
    async with AsyncSessionLocal() as db:
        query = select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True))
        if org_id is not None:
            query = query.where(WebhookEndpoint.organization_id == org_id)
        endpoints = list((await db.execute(query)).scalars().all())
        if not apply:
            return len(endpoints)
        for endpoint in endpoints:
            endpoint.secret_encrypted = encrypt_token(secrets.token_hex(32))
            endpoint.updated_at = datetime.now(UTC)
        await db.commit()
        return len(endpoints)


async def main_async() -> int:
    args = _args()
    total_integrations, connected_integrations = await _count_integrations(args.organization_id)
    rotated = await _rotate_webhook_secrets(apply=args.apply, org_id=args.organization_id)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Rotation drill mode: {mode}")
    print(f"Scope: organization_id={args.organization_id if args.organization_id is not None else 'ALL'}")
    print(f"Integrations total={total_integrations}, connected={connected_integrations}")
    print(f"Webhook endpoints {'rotated' if args.apply else 'planned'}={rotated}")
    print("Post-rotation checklist:")
    print("- Run /api/v1/integrations/token-health and verify no critical providers are stale.")
    print("- Send /api/v1/webhooks/{id}/test for at least one endpoint per org.")
    print("- Verify audit logs include rotation drill metadata.")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
