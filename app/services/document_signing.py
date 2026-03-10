"""Document signing service."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_signing import SignatureRequest


async def create_request(
    db: AsyncSession, *, organization_id: int, title: str,
    document_url: str | None = None, deal_id: int | None = None,
    contact_id: int | None = None, signing_order: int = 1,
    signers: list[dict] | None = None, expires_at=None,
    sent_by_user_id: int | None = None,
) -> SignatureRequest:
    row = SignatureRequest(
        organization_id=organization_id, title=title,
        document_url=document_url, deal_id=deal_id,
        contact_id=contact_id, signing_order=signing_order,
        signers_json=json.dumps(signers or []),
        expires_at=expires_at, sent_by_user_id=sent_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_requests(
    db: AsyncSession, organization_id: int, *,
    status: str | None = None, deal_id: int | None = None,
) -> list[SignatureRequest]:
    q = select(SignatureRequest).where(SignatureRequest.organization_id == organization_id)
    if status:
        q = q.where(SignatureRequest.status == status)
    if deal_id is not None:
        q = q.where(SignatureRequest.deal_id == deal_id)
    q = q.order_by(SignatureRequest.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_request(db: AsyncSession, request_id: int, organization_id: int) -> SignatureRequest | None:
    q = select(SignatureRequest).where(SignatureRequest.id == request_id, SignatureRequest.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def mark_signed(db: AsyncSession, request_id: int, organization_id: int) -> SignatureRequest | None:
    row = await get_request(db, request_id, organization_id)
    if not row:
        return None
    row.status = "signed"
    row.signed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def mark_declined(db: AsyncSession, request_id: int, organization_id: int) -> SignatureRequest | None:
    row = await get_request(db, request_id, organization_id)
    if not row:
        return None
    row.status = "declined"
    await db.commit()
    await db.refresh(row)
    return row


async def get_stats(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(SignatureRequest.status, func.count(SignatureRequest.id))
        .where(SignatureRequest.organization_id == organization_id)
        .group_by(SignatureRequest.status)
    )).all()
    return {status: count for status, count in rows}
