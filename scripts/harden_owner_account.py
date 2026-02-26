from __future__ import annotations

# ruff: noqa: E402

import asyncio
from pathlib import Path
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models import organization as _model_organization  # noqa: F401
from app.models.user import User

_DEMO_EMAILS = {"demo@ai.com", "demo@local.ai"}


def _backup_sqlite_if_local() -> None:
    db_url = (settings.DATABASE_URL or "").strip()
    if not db_url.startswith("sqlite"):
        return
    # Handles sqlite:///./personal_clone.db style values.
    candidate = db_url.split("sqlite:///", 1)[-1].strip()
    if not candidate:
        return
    db_path = Path(candidate).resolve()
    if not db_path.exists():
        return
    backup_dir = Path("Data") / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}.owner_backup{db_path.suffix}"
    backup_path.write_bytes(db_path.read_bytes())
    print(f"[backup] created {backup_path}")


async def _run() -> int:
    owner_email = (settings.ADMIN_EMAIL or "").strip().lower()
    owner_name = (settings.ADMIN_NAME or "Owner").strip()
    owner_password = settings.ADMIN_PASSWORD
    if not owner_email or "@" not in owner_email:
        print("[error] ADMIN_EMAIL is missing/invalid in .env")
        return 1
    if not owner_password or len(owner_password) < 8:
        print("[error] ADMIN_PASSWORD is missing/too short in .env")
        return 1

    _backup_sqlite_if_local()

    async with AsyncSessionLocal() as db:
        owner = (
            await db.execute(select(User).where(User.email == owner_email))
        ).scalar_one_or_none()

        if owner is None:
            demo = (
                await db.execute(
                    select(User)
                    .where(User.email.in_(tuple(_DEMO_EMAILS)))
                    .order_by(User.id.asc())
                )
            ).scalars().first()
            if demo is not None:
                demo.email = owner_email
                demo.name = owner_name
                demo.role = "CEO"
                demo.is_active = True
                demo.password_hash = hash_password(owner_password)
                owner = demo
                print(f"[owner] promoted demo user id={owner.id} -> {owner_email}")
            else:
                owner = User(
                    organization_id=1,
                    name=owner_name,
                    email=owner_email,
                    password_hash=hash_password(owner_password),
                    role="CEO",
                    is_active=True,
                )
                db.add(owner)
                print(f"[owner] created owner account {owner_email}")
        else:
            owner.name = owner_name
            owner.role = "CEO"
            owner.is_active = True
            owner.password_hash = hash_password(owner_password)
            print(f"[owner] updated existing owner id={owner.id} email={owner_email}")

        demo_rows = (
            await db.execute(
                select(User).where(
                    User.email.in_(tuple(_DEMO_EMAILS)),
                    User.email != owner_email,
                    User.is_active.is_(True),
                )
            )
        ).scalars().all()
        disabled = 0
        for row in demo_rows:
            row.is_active = False
            row.role = "STAFF"
            disabled += 1

        await db.commit()
        print(f"[done] owner={owner_email} demo_accounts_disabled={disabled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
