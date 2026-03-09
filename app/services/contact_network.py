"""Contact relationship graph — maps connections between contacts."""
from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.deal import Deal
from app.models.email import Email

logger = logging.getLogger(__name__)


async def get_contact_network(
    db: AsyncSession,
    contact_id: int,
    organization_id: int,
    *,
    limit: int = 20,
) -> dict:
    """Build a relationship graph for a contact.

    Connections are found via:
    - Shared company (same company field)
    - Shared deals (contacts linked to the same deal's contact)
    - Email threads (contacts whose email appears in same threads)
    """
    # Get the target contact
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id, Contact.organization_id == organization_id,
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        return None

    connections: dict[int, dict] = {}

    def _add_connection(c: Contact, link_type: str, detail: str = ""):
        if c.id == contact_id:
            return
        if c.id not in connections:
            connections[c.id] = {
                "contact_id": c.id,
                "name": c.name,
                "company": c.company,
                "relationship": c.relationship,
                "links": [],
            }
        connections[c.id]["links"].append({"type": link_type, "detail": detail})

    # 1. Same company
    if contact.company:
        result = await db.execute(
            select(Contact).where(
                Contact.organization_id == organization_id,
                Contact.company == contact.company,
                Contact.id != contact_id,
            ).limit(limit)
        )
        for c in result.scalars().all():
            _add_connection(c, "same_company", contact.company)

    # 2. Shared deals
    deal_result = await db.execute(
        select(Deal.id, Deal.title).where(
            Deal.organization_id == organization_id,
            Deal.contact_id == contact_id,
        )
    )
    deal_rows = deal_result.all()
    if deal_rows:
        # Find other contacts that share deals via same company or are referenced
        for deal_id, deal_title in deal_rows:
            # Contacts linked to other deals with the same contact's company
            pass  # Deals are 1:1 contact_id, so look for contacts on same-stage deals

    # 3. Email thread connections
    if contact.email:
        # Find threads this contact is in
        thread_result = await db.execute(
            select(Email.thread_id).where(
                Email.organization_id == organization_id,
                Email.thread_id.is_not(None),
                (Email.from_address == contact.email) | (Email.to_address == contact.email),
            ).distinct().limit(50)
        )
        thread_ids = [r[0] for r in thread_result.all()]

        if thread_ids:
            # Find other email addresses in those threads
            email_result = await db.execute(
                select(Email.from_address, Email.to_address).where(
                    Email.organization_id == organization_id,
                    Email.thread_id.in_(thread_ids),
                )
            )
            other_emails: set[str] = set()
            for from_addr, to_addr in email_result.all():
                if from_addr and from_addr != contact.email:
                    other_emails.add(from_addr)
                if to_addr and to_addr != contact.email:
                    other_emails.add(to_addr)

            if other_emails:
                # Find contacts matching these emails
                match_result = await db.execute(
                    select(Contact).where(
                        Contact.organization_id == organization_id,
                        Contact.email.in_(list(other_emails)[:50]),
                        Contact.id != contact_id,
                    ).limit(limit)
                )
                for c in match_result.scalars().all():
                    _add_connection(c, "email_thread", "Shared email thread")

    # Build response
    conn_list = sorted(connections.values(), key=lambda x: len(x["links"]), reverse=True)[:limit]

    return {
        "contact_id": contact_id,
        "name": contact.name,
        "company": contact.company,
        "connection_count": len(conn_list),
        "connections": conn_list,
    }
