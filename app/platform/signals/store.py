"""Signal storage primitives."""

from collections.abc import Iterable
from typing import Protocol

from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal
from app.platform.signals.schemas import SignalEnvelope


def _to_envelope(row: Signal) -> SignalEnvelope:
    return SignalEnvelope(
        signal_id=row.signal_id,
        topic=row.topic,
        category=row.category,
        organization_id=row.organization_id,
        workspace_id=row.workspace_id,
        actor_user_id=row.actor_user_id,
        source=row.source,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        occurred_at=row.occurred_at,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        request_id=row.request_id,
        summary_text=row.summary_text,
        payload=row.payload_json or {},
        metadata=row.metadata_json or {},
    )


class SignalStore(Protocol):
    """Persistence interface for signal envelopes."""

    async def append(self, signal: SignalEnvelope, *, db: AsyncSession | None = None) -> SignalEnvelope:
        """Persist a signal and return the stored record."""

    async def list_recent(
        self,
        *,
        db: AsyncSession | None = None,
        limit: int = 100,
        organization_id: int | None = None,
        topic: str | None = None,
    ) -> list[SignalEnvelope]:
        """Return recent signals in reverse chronological order."""


class InMemorySignalStore:
    """Small in-process signal store for tests and fallback runtime use."""

    def __init__(self, seed: Iterable[SignalEnvelope] | None = None) -> None:
        self._signals: list[SignalEnvelope] = list(seed or [])

    async def append(self, signal: SignalEnvelope, *, db: AsyncSession | None = None) -> SignalEnvelope:
        del db
        self._signals.append(signal)
        return signal

    async def list_recent(
        self,
        *,
        db: AsyncSession | None = None,
        limit: int = 100,
        organization_id: int | None = None,
        topic: str | None = None,
    ) -> list[SignalEnvelope]:
        del db
        rows = self._signals
        if organization_id is not None:
            rows = [row for row in rows if row.organization_id == organization_id]
        if topic is not None:
            rows = [row for row in rows if row.topic == topic]
        return list(reversed(rows[-limit:]))


class SqlAlchemySignalStore:
    """Official signal store backed by the signals table."""

    async def append(self, signal: SignalEnvelope, *, db: AsyncSession | None = None) -> SignalEnvelope:
        if db is None:
            raise ValueError("SqlAlchemySignalStore.append requires an AsyncSession")
        row = Signal(
            signal_id=signal.signal_id,
            organization_id=signal.organization_id,
            workspace_id=signal.workspace_id,
            actor_user_id=signal.actor_user_id,
            topic=signal.topic,
            category=signal.category.value,
            source=signal.source,
            entity_type=signal.entity_type,
            entity_id=signal.entity_id,
            correlation_id=signal.correlation_id,
            causation_id=signal.causation_id,
            occurred_at=signal.occurred_at,
            payload_json=signal.payload,
            metadata_json=signal.metadata,
            request_id=signal.request_id,
            summary_text=signal.summary_text,
        )
        db.add(row)
        await db.flush()
        return signal

    async def list_recent(
        self,
        *,
        db: AsyncSession | None = None,
        limit: int = 100,
        organization_id: int | None = None,
        topic: str | None = None,
    ) -> list[SignalEnvelope]:
        if db is None:
            raise ValueError("SqlAlchemySignalStore.list_recent requires an AsyncSession")
        query: Select[tuple[Signal]] = select(Signal).order_by(desc(Signal.occurred_at), desc(Signal.id))
        if organization_id is not None:
            query = query.where(Signal.organization_id == organization_id)
        if topic is not None:
            query = query.where(Signal.topic == topic)
        result = await db.execute(query.limit(limit))
        return [_to_envelope(row) for row in result.scalars().all()]
