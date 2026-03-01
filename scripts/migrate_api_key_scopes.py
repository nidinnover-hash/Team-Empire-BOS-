from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

# Keep aligned with top-level API resources.
DEFAULT_RESOURCES: tuple[str, ...] = (
    "admin",
    "agents",
    "api_keys",
    "approvals",
    "auth",
    "briefing",
    "commands",
    "contacts",
    "control",
    "dashboard_kpi",
    "data_collection",
    "email",
    "executions",
    "export",
    "finance",
    "github",
    "goals",
    "health",
    "inbox",
    "integrations",
    "intelligence",
    "layers",
    "memory",
    "mfa",
    "notes",
    "notifications",
    "observability",
    "ops",
    "orgs",
    "projects",
    "search",
    "social",
    "tasks",
    "users",
    "webhooks",
)


@dataclass(frozen=True)
class PlanEntry:
    key_id: int
    old_scopes: str
    new_scopes: str


def _normalize_list(raw: str) -> list[str]:
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _phase1_target(scopes: str) -> str | None:
    parts = _normalize_list(scopes)
    if not parts:
        return None
    unique = tuple(dict.fromkeys(parts))
    if unique == ("read",):
        return "api:read"
    if unique == ("write",):
        return "api:write"
    if set(unique) == {"read", "write"}:
        return "api:*"
    return None


def _phase2_target(scopes: str, resources: tuple[str, ...]) -> str | None:
    parts = _normalize_list(scopes)
    if not parts:
        return None
    unique = tuple(dict.fromkeys(parts))

    def all_read() -> str:
        return ",".join(f"{r}:read" for r in resources)

    def all_write() -> str:
        return ",".join(f"{r}:write" for r in resources)

    def all_full() -> str:
        return ",".join(f"{r}:*" for r in resources)

    if unique in {("read",), ("api:read",)}:
        return all_read()
    if unique in {("write",), ("api:write",)}:
        return all_write()
    if set(unique) == {"read", "write"} or unique == ("api:*",):
        return all_full()
    return None


def _target_scopes(scopes: str, profile: str, resources: tuple[str, ...]) -> str | None:
    if profile == "phase1":
        return _phase1_target(scopes)
    if profile == "phase2":
        return _phase2_target(scopes, resources)
    return None


async def _build_plan(*, profile: str, organization_id: int | None, resources: tuple[str, ...]) -> list[PlanEntry]:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.api_key import ApiKey

    async with AsyncSessionLocal() as db:
        query = select(ApiKey).where(ApiKey.is_active.is_(True))
        if organization_id is not None:
            query = query.where(ApiKey.organization_id == organization_id)
        result = await db.execute(query.order_by(ApiKey.id.asc()))
        items = list(result.scalars().all())
        plan: list[PlanEntry] = []
        for key in items:
            old = (key.scopes or "").strip()
            if not old:
                continue
            target = _target_scopes(old, profile, resources)
            if not target or target == old:
                continue
            plan.append(PlanEntry(key_id=int(key.id), old_scopes=old, new_scopes=target))
        return plan


async def _apply_plan(plan: list[PlanEntry]) -> int:
    if not plan:
        return 0
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.api_key import ApiKey

    by_id = {entry.key_id: entry for entry in plan}
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ApiKey).where(ApiKey.id.in_(list(by_id.keys()))))
        items = list(result.scalars().all())
        for key in items:
            entry = by_id.get(int(key.id))
            if entry is None:
                continue
            key.scopes = entry.new_scopes
        await db.commit()
    return len(plan)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy API key scopes to explicit scope formats. "
            "Default mode is dry-run."
        )
    )
    parser.add_argument(
        "--profile",
        choices=("phase1", "phase2"),
        default="phase1",
        help=(
            "phase1: read/write -> api:* family. "
            "phase2: read/write/api:* -> resource-specific scopes."
        ),
    )
    parser.add_argument(
        "--organization-id",
        type=int,
        default=None,
        help="Only migrate keys in one organization.",
    )
    parser.add_argument(
        "--resources",
        default=",".join(DEFAULT_RESOURCES),
        help="Comma-separated resource names used by phase2 profile.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag, script runs in dry-run mode.",
    )
    return parser.parse_args()


async def _main_async() -> int:
    args = _parse_args()
    resources = tuple(part.strip().lower() for part in args.resources.split(",") if part.strip())
    if not resources:
        print("No resources provided.")
        return 2

    plan = await _build_plan(
        profile=args.profile,
        organization_id=args.organization_id,
        resources=resources,
    )
    if not plan:
        print("No API keys require migration.")
        return 0

    print(f"Planned migrations: {len(plan)} (profile={args.profile}, apply={args.apply})")
    for entry in plan:
        print(f"- key_id={entry.key_id}  {entry.old_scopes!r} -> {entry.new_scopes!r}")

    if not args.apply:
        print("Dry run complete. Re-run with --apply to persist.")
        return 0

    updated = await _apply_plan(plan)
    print(f"Updated API keys: {updated}")
    return 0


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
