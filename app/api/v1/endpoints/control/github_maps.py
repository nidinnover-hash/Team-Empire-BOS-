"""GitHub identity mapping endpoints."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.ceo_control import GitHubIdentityMap
from app.schemas.control import (
    GitHubIdentityMapListRead,
    GitHubIdentityMapUpsertRead,
    GitHubIdentityMapUpsertRequest,
)

router = APIRouter()


@router.get("/github-identity-map", response_model=GitHubIdentityMapListRead)
async def github_identity_map_list(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> GitHubIdentityMapListRead:
    org_id = int(actor["org_id"])
    rows = (
        await db.execute(
            select(GitHubIdentityMap)
            .where(GitHubIdentityMap.organization_id == org_id)
            .order_by(GitHubIdentityMap.company_email.asc())
        )
    ).scalars().all()
    return GitHubIdentityMapListRead(
        count=len(rows),
        items=[
            {  # type: ignore[misc]
                "company_email": row.company_email,
                "github_login": row.github_login,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ],
    )


@router.post("/github-identity-map/upsert", response_model=GitHubIdentityMapUpsertRead)
async def github_identity_map_upsert(
    payload: GitHubIdentityMapUpsertRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubIdentityMapUpsertRead:
    org_id = int(actor["org_id"])
    company_email = payload.company_email.strip().lower()
    github_login = payload.github_login.strip().lower()
    now = datetime.now(UTC)

    existing = (
        await db.execute(
            select(GitHubIdentityMap).where(
                GitHubIdentityMap.organization_id == org_id,
                GitHubIdentityMap.company_email == company_email,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.github_login = github_login
        existing.updated_at = now
    else:
        db.add(
            GitHubIdentityMap(
                organization_id=org_id,
                company_email=company_email,
                github_login=github_login,
                created_at=now,
                updated_at=now,
            )
        )
    await db.commit()
    return GitHubIdentityMapUpsertRead(ok=True, company_email=company_email, github_login=github_login)
