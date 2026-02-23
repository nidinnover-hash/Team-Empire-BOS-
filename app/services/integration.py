from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from typing import cast

from app.core.token_crypto import decrypt_config, encrypt_config
from app.models.integration import Integration


def _validate_token_fields(config_json: dict) -> None:
    for field in ("access_token", "refresh_token", "api_token"):
        value = config_json.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"Integration token field '{field}' must be a string")


def _decrypted(integration: Integration) -> Integration:
    """
    Return the integration with config_json tokens decrypted in-place (on the
    loaded object). Does NOT write to DB. Used so callers always get plaintext
    tokens for API calls.
    """
    # Keep decrypted tokens available to callers without marking config_json dirty.
    # This prevents accidental plaintext persistence on unrelated commits.
    set_committed_value(integration, "config_json", decrypt_config(integration.config_json or {}))
    return integration


async def list_integrations(
    db: AsyncSession, organization_id: int, limit: int = 100
) -> list[Integration]:
    result = await db.execute(
        select(Integration)
        .where(Integration.organization_id == organization_id)
        .order_by(Integration.created_at.desc())
        .limit(limit)
    )
    return [_decrypted(i) for i in result.scalars().all()]


async def get_integration(
    db: AsyncSession, integration_id: int, organization_id: int
) -> Integration | None:
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.organization_id == organization_id,
        )
    )
    item = result.scalar_one_or_none()
    return _decrypted(item) if item else None


async def get_integration_by_type(
    db: AsyncSession, organization_id: int, integration_type: str
) -> Integration | None:
    result = await db.execute(
        select(Integration).where(
            Integration.organization_id == organization_id,
            Integration.type == integration_type,
        )
    )
    item = result.scalar_one_or_none()
    return _decrypted(item) if item else None


async def connect_integration(
    db: AsyncSession,
    organization_id: int,
    integration_type: str,
    config_json: dict,
) -> Integration:
    _validate_token_fields(config_json)
    encrypted = encrypt_config(config_json)
    existing = await get_integration_by_type(db, organization_id, integration_type)
    if existing is not None:
        # get_integration_by_type returns decrypted object; re-encrypt for storage
        existing.config_json = encrypted
        existing.status = "connected"
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return _decrypted(existing)

    item = Integration(
        organization_id=organization_id,
        type=integration_type,
        config_json=encrypted,
        status="connected",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _decrypted(item)


async def disconnect_integration(
    db: AsyncSession, integration_id: int, organization_id: int
) -> Integration | None:
    item = await get_integration(db, integration_id, organization_id)
    if item is None:
        return None
    item.status = "disconnected"
    item.updated_at = datetime.now(timezone.utc)
    item.config_json = encrypt_config(item.config_json or {})
    await db.commit()
    await db.refresh(item)
    return _decrypted(item)


async def mark_sync_time(
    db: AsyncSession, integration: Integration
) -> Integration:
    now = datetime.now(timezone.utc)
    integration.last_sync_at = now
    integration.updated_at = now
    # Re-encrypt config before committing — _decrypted() may have mutated the ORM
    # object to plaintext in-place; always encrypt so tokens are never stored raw.
    integration.config_json = encrypt_config(integration.config_json or {})
    await db.commit()
    await db.refresh(integration)
    return integration


async def find_whatsapp_integration_by_phone_number_id(
    db: AsyncSession,
    phone_number_id: str,
) -> Integration | None:
    """
    Resolve WhatsApp integration for an incoming webhook by phone_number_id.
    phone_number_id is stored in config_json for whatsapp_business.
    """
    result = await db.execute(
        select(Integration).where(
            Integration.type == "whatsapp_business",
            Integration.status == "connected",
        )
    )
    for item in result.scalars().all():
        cfg = decrypt_config(item.config_json or {})
        if cfg.get("phone_number_id") == phone_number_id:
            set_committed_value(item, "config_json", cfg)
            return cast(Integration, item)
    return None
