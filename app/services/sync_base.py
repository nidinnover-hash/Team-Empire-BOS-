"""
Base class for integration sync operations.

Standardizes the fetch → dedup → persist pattern used across
Notion, HubSpot, Calendly (and future integrations).

Subclasses implement four hooks:
  - fetch_items()       — call external API, return raw dicts
  - load_existing_keys() — one query to pre-load dedup keys from DB
  - dedup_key()          — extract hashable key from a raw API item
  - to_model()           — convert raw item to ORM model instance
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Hashable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import run_with_retry
from app.db.base import Base as ORMBase
from app.services.integration import get_integration_by_type, mark_sync_time

logger = logging.getLogger(__name__)

_MAX_ERROR_LOG = 20  # cap per-item error messages in SyncResult


@dataclass
class SyncResult:
    """Typed return value for all sync operations."""

    provider: str
    synced: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    last_sync_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Backward-compatible dict representation."""
        d: dict[str, Any] = {
            "synced": self.synced,
            "skipped": self.skipped,
            "last_sync_at": self.last_sync_at.isoformat(),
        }
        if self.errors:
            d["errors"] = self.errors
        d.update(self.extra)
        return d


class IntegrationSync(ABC):
    """Abstract base for integrations that sync external data to local DB models."""

    provider: str  # e.g. "notion", "hubspot", "calendly"

    @abstractmethod
    async def fetch_items(self, token: str, config: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch raw items from the external API.

        Subclass is responsible for pagination.
        ``config`` is the full integration config_json (may contain user_uri, etc.).
        """

    @abstractmethod
    async def load_existing_keys(self, db: AsyncSession, org_id: int) -> set[Hashable]:
        """Pre-load dedup keys from the database (single query, no N+1)."""

    @abstractmethod
    def dedup_key(self, item: dict[str, Any]) -> Hashable:
        """Return a hashable key for dedup (e.g. title, email, (name, date) tuple)."""

    @abstractmethod
    def to_model(self, item: dict[str, Any], org_id: int) -> ORMBase:
        """Convert a raw API item to an ORM model instance ready for db.add()."""

    def _token_field(self) -> str:
        """Config JSON key that holds the API token. Override if different."""
        return "access_token"

    async def sync(self, db: AsyncSession, org_id: int, **kwargs: Any) -> SyncResult:
        """Template method: get token → fetch → dedup → persist → mark sync.

        Subclasses should NOT override this; customise the hooks instead.
        Extra ``kwargs`` are forwarded to ``fetch_items()``.
        """
        result = SyncResult(provider=self.provider)

        # 1. Look up integration + token
        integration = await get_integration_by_type(db, org_id, self.provider)
        if not integration or integration.status != "connected":
            raise ValueError(f"{self.provider.title()} not connected")

        config = integration.config_json or {}
        token = config.get(self._token_field(), "")

        # 2. Fetch items from external API (with retry)
        try:
            items = await run_with_retry(
                lambda: self.fetch_items(token, config, **kwargs),
            )
        except Exception as exc:
            logger.warning("%s fetch failed: %s", self.provider, exc)
            result.errors.append(f"fetch: {type(exc).__name__}: {str(exc)[:200]}")
            await mark_sync_time(db, integration)
            return result

        # 3. Pre-load dedup keys
        existing_keys = await self.load_existing_keys(db, org_id)

        # 4. Convert + dedup + persist
        for item in items:
            try:
                key = self.dedup_key(item)
                if key in existing_keys:
                    result.skipped += 1
                    continue

                model = self.to_model(item, org_id)
                db.add(model)
                existing_keys.add(key)  # intra-batch dedup
                result.synced += 1
            except Exception as exc:
                if len(result.errors) < _MAX_ERROR_LOG:
                    result.errors.append(f"item: {type(exc).__name__}: {str(exc)[:200]}")
                result.skipped += 1

        # 5. Commit + mark sync time
        if result.synced:
            await db.commit()
        await mark_sync_time(db, integration)
        result.last_sync_at = datetime.now(UTC)

        logger.info(
            "%s sync for org %d: synced=%d skipped=%d errors=%d",
            self.provider, org_id, result.synced, result.skipped, len(result.errors),
        )
        return result
