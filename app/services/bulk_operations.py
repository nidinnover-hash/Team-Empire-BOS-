"""Bulk operations — CSV import and batch operations for contacts, tasks, projects."""
from __future__ import annotations

import contextlib
import csv
import io
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Maximum rows per import to prevent abuse
MAX_IMPORT_ROWS = 1000


async def import_contacts_csv(
    db: AsyncSession,
    organization_id: int,
    csv_text: str,
) -> dict:
    """Import contacts from CSV text. Expected columns: name, email, phone, company, role, relationship, pipeline_stage, tags.

    Returns {imported, skipped, errors}.
    """
    from app.models.contact import Contact

    reader = csv.DictReader(io.StringIO(csv_text))
    imported = 0
    skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader):
        if i >= MAX_IMPORT_ROWS:
            errors.append(f"Row limit reached ({MAX_IMPORT_ROWS}). Remaining rows skipped.")
            break

        name = (row.get("name") or "").strip()
        if not name:
            skipped += 1
            errors.append(f"Row {i + 2}: missing required 'name' field")
            continue

        email = (row.get("email") or "").strip() or None
        phone = (row.get("phone") or "").strip() or None

        # Skip if exact duplicate by email
        if email:
            existing = await db.execute(
                select(Contact.id).where(
                    Contact.organization_id == organization_id,
                    Contact.email == email,
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

        relationship = (row.get("relationship") or "personal").strip().lower()
        if relationship not in ("personal", "business", "family", "mentor", "other"):
            relationship = "personal"

        pipeline = (row.get("pipeline_stage") or "new").strip().lower()
        if pipeline not in ("new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"):
            pipeline = "new"

        contact = Contact(
            organization_id=organization_id,
            name=name[:500],
            email=email,
            phone=phone,
            company=(row.get("company") or "").strip()[:500] or None,
            role=(row.get("role") or "").strip()[:200] or None,
            relationship=relationship,
            pipeline_stage=pipeline,
            lead_score=0,
            lead_type="general",
            routing_status="unrouted",
            qualified_status="unqualified",
            lead_owner_company_id=1,
            tags=(row.get("tags") or "").strip()[:500] or None,
        )
        db.add(contact)
        imported += 1

    if imported > 0:
        await db.commit()

    logger.info("CSV import: %d imported, %d skipped for org %d", imported, skipped, organization_id)
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


async def import_tasks_csv(
    db: AsyncSession,
    organization_id: int,
    csv_text: str,
) -> dict:
    """Import tasks from CSV text. Expected columns: title, description, priority, category, due_date, project_id.

    Returns {imported, skipped, errors}.
    """
    from app.models.task import Task

    reader = csv.DictReader(io.StringIO(csv_text))
    imported = 0
    skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader):
        if i >= MAX_IMPORT_ROWS:
            errors.append(f"Row limit reached ({MAX_IMPORT_ROWS}). Remaining rows skipped.")
            break

        title = (row.get("title") or "").strip()
        if not title:
            skipped += 1
            errors.append(f"Row {i + 2}: missing required 'title' field")
            continue

        try:
            priority = int(row.get("priority", 2))
            priority = max(1, min(4, priority))
        except (ValueError, TypeError):
            priority = 2

        category = (row.get("category") or "personal").strip().lower()
        if category not in ("personal", "business", "health", "finance", "other"):
            category = "personal"

        due_date = None
        raw_due = (row.get("due_date") or "").strip()
        if raw_due:
            with contextlib.suppress(ValueError):
                due_date = datetime.strptime(raw_due, "%Y-%m-%d").date()

        project_id = None
        raw_project = (row.get("project_id") or "").strip()
        if raw_project:
            with contextlib.suppress(ValueError):
                project_id = int(raw_project)

        task = Task(
            organization_id=organization_id,
            title=title[:500],
            description=(row.get("description") or "").strip()[:2000] or None,
            priority=priority,
            category=category,
            due_date=due_date,
            project_id=project_id,
        )
        db.add(task)
        imported += 1

    if imported > 0:
        await db.commit()

    logger.info("CSV task import: %d imported, %d skipped for org %d", imported, skipped, organization_id)
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


async def import_deals_csv(
    db: AsyncSession,
    organization_id: int,
    csv_text: str,
) -> dict:
    """Import deals from CSV. Columns: title, value, stage, probability, expected_close_date, contact_id, description, source.

    Returns {imported, skipped, errors}.
    """
    from app.models.deal import DEAL_STAGES, Deal

    reader = csv.DictReader(io.StringIO(csv_text))
    imported = 0
    skipped = 0
    errors: list[str] = []

    for i, row in enumerate(reader):
        if i >= MAX_IMPORT_ROWS:
            errors.append(f"Row limit reached ({MAX_IMPORT_ROWS}). Remaining rows skipped.")
            break

        title = (row.get("title") or "").strip()
        if not title:
            skipped += 1
            errors.append(f"Row {i + 2}: missing required 'title' field")
            continue

        try:
            value = float(row.get("value", 0))
        except (ValueError, TypeError):
            value = 0

        stage = (row.get("stage") or "discovery").strip().lower()
        if stage not in DEAL_STAGES:
            stage = "discovery"

        try:
            probability = int(row.get("probability", 0))
            probability = max(0, min(100, probability))
        except (ValueError, TypeError):
            probability = 0

        expected_close = None
        raw_close = (row.get("expected_close_date") or "").strip()
        if raw_close:
            with contextlib.suppress(ValueError):
                expected_close = datetime.strptime(raw_close, "%Y-%m-%d").date()

        contact_id = None
        raw_contact = (row.get("contact_id") or "").strip()
        if raw_contact:
            with contextlib.suppress(ValueError):
                contact_id = int(raw_contact)

        deal = Deal(
            organization_id=organization_id,
            title=title[:300],
            value=value,
            stage=stage,
            probability=probability,
            expected_close_date=expected_close,
            contact_id=contact_id,
            description=(row.get("description") or "").strip()[:2000] or None,
            source=(row.get("source") or "").strip()[:100] or None,
        )
        db.add(deal)
        imported += 1

    if imported > 0:
        await db.commit()

    logger.info("CSV deal import: %d imported, %d skipped for org %d", imported, skipped, organization_id)
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


async def batch_delete_contacts(
    db: AsyncSession,
    organization_id: int,
    contact_ids: list[int],
) -> dict:
    """Delete multiple contacts by ID. Returns {deleted, not_found}."""
    from app.models.contact import Contact

    deleted = 0
    not_found = 0

    for cid in contact_ids[:500]:
        result = await db.execute(
            select(Contact).where(
                Contact.id == cid, Contact.organization_id == organization_id,
            )
        )
        contact = result.scalar_one_or_none()
        if contact:
            await db.delete(contact)
            deleted += 1
        else:
            not_found += 1

    if deleted > 0:
        await db.commit()

    return {"deleted": deleted, "not_found": not_found}


async def batch_update_contacts_stage(
    db: AsyncSession,
    organization_id: int,
    contact_ids: list[int],
    pipeline_stage: str,
) -> dict:
    """Move multiple contacts to a pipeline stage. Returns {updated, not_found}."""
    from app.models.contact import PIPELINE_STAGES, Contact

    if pipeline_stage not in PIPELINE_STAGES:
        return {"error": f"Invalid stage. Must be one of: {', '.join(PIPELINE_STAGES)}"}

    updated = 0
    not_found = 0

    for cid in contact_ids[:500]:
        result = await db.execute(
            select(Contact).where(
                Contact.id == cid, Contact.organization_id == organization_id,
            )
        )
        contact = result.scalar_one_or_none()
        if contact:
            contact.pipeline_stage = pipeline_stage
            contact.updated_at = datetime.now(UTC)
            updated += 1
        else:
            not_found += 1

    if updated > 0:
        await db.commit()

    return {"updated": updated, "not_found": not_found}
