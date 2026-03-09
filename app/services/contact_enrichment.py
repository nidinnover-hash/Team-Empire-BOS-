"""Contact enrichment pipeline — auto-enrich contacts with derived data.

Runs as a background task after contact creation. Enriches:
- Timezone from email domain (simple heuristic)
- Company name from email domain
- Auto-tags based on relationship/source
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact

logger = logging.getLogger(__name__)

# Common email domain → company name mapping
_DOMAIN_COMPANIES: dict[str, str] = {
    "google.com": "Google",
    "microsoft.com": "Microsoft",
    "apple.com": "Apple",
    "amazon.com": "Amazon",
    "meta.com": "Meta",
    "facebook.com": "Meta",
    "salesforce.com": "Salesforce",
    "hubspot.com": "HubSpot",
    "stripe.com": "Stripe",
    "shopify.com": "Shopify",
}

# Domain suffix → timezone hint
_DOMAIN_TZ_HINTS: dict[str, str] = {
    ".uk": "Europe/London",
    ".de": "Europe/Berlin",
    ".fr": "Europe/Paris",
    ".jp": "Asia/Tokyo",
    ".au": "Australia/Sydney",
    ".in": "Asia/Kolkata",
    ".sg": "Asia/Singapore",
    ".ae": "Asia/Dubai",
    ".ca": "America/Toronto",
    ".br": "America/Sao_Paulo",
}


def _extract_domain(email: str | None) -> str | None:
    """Extract domain from email address."""
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].strip().lower()


def _guess_company(domain: str | None) -> str | None:
    """Guess company name from email domain."""
    if not domain:
        return None
    if domain in _DOMAIN_COMPANIES:
        return _DOMAIN_COMPANIES[domain]
    # Skip free email providers
    if domain in {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "protonmail.com"}:
        return None
    # Use the domain name itself as company hint
    parts = domain.split(".")
    if len(parts) >= 2:
        name = parts[0].replace("-", " ").replace("_", " ").title()
        if len(name) > 2:
            return name
    return None


def _guess_timezone(domain: str | None) -> str | None:
    """Guess timezone from email domain TLD."""
    if not domain:
        return None
    for suffix, tz in _DOMAIN_TZ_HINTS.items():
        if domain.endswith(suffix):
            return tz
    return None


def _auto_lead_score(contact: Contact) -> int:
    """Calculate initial lead score based on available data."""
    score = 0
    if contact.email:
        score += 10
    if contact.phone:
        score += 10
    if contact.company:
        score += 15
    if contact.relationship in ("business", "client"):
        score += 20
    elif contact.relationship == "partner":
        score += 15
    if contact.source:
        score += 5
    return min(score, 100)


async def enrich_contact(db: AsyncSession, contact_id: int, organization_id: int) -> dict:
    """Enrich a contact with derived data. Returns dict of fields updated."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.organization_id == organization_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        return {"status": "not_found"}

    updated: dict[str, str] = {}
    domain = _extract_domain(contact.email)

    # Enrich company if blank
    if not contact.company and domain:
        company = _guess_company(domain)
        if company:
            contact.company = company
            updated["company"] = company

    # Enrich timezone if blank
    if not getattr(contact, "timezone", None) and domain:
        tz = _guess_timezone(domain)
        if tz and hasattr(contact, "timezone"):
            contact.timezone = tz
            updated["timezone"] = tz

    # Auto-set lead score if zero
    if (contact.lead_score or 0) == 0:
        score = _auto_lead_score(contact)
        if score > 0:
            contact.lead_score = score
            updated["lead_score"] = str(score)

    if updated:
        await db.commit()
        await db.refresh(contact)
        logger.info("Enriched contact %d: %s", contact_id, updated)

    return {"contact_id": contact_id, "enriched_fields": updated}


async def enrich_contact_background(contact_id: int, organization_id: int) -> None:
    """Fire-and-forget enrichment. Opens its own DB session."""
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await enrich_contact(db, contact_id, organization_id)
    except Exception:
        logger.warning("Background enrichment failed for contact %d", contact_id, exc_info=True)


async def batch_enrich(db: AsyncSession, organization_id: int, limit: int = 100) -> dict:
    """Enrich all contacts that have no company set. Returns count of enriched."""
    result = await db.execute(
        select(Contact).where(
            Contact.organization_id == organization_id,
            (Contact.company.is_(None)) | (Contact.company == ""),
            Contact.email.isnot(None),
        ).limit(limit)
    )
    contacts = list(result.scalars().all())
    enriched = 0
    for c in contacts:
        r = await enrich_contact(db, c.id, organization_id)
        if r.get("enriched_fields"):
            enriched += 1
    return {"total_checked": len(contacts), "enriched": enriched}
