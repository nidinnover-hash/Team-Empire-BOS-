"""In-process signal publishing and subscription."""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.signals.schemas import SignalEnvelope
from app.platform.signals.store import SignalStore

logger = logging.getLogger(__name__)

SignalHandler = Callable[[SignalEnvelope], Awaitable[None]]


class SignalPublisher(Protocol):
    """Publish signals and notify in-process subscribers."""

    async def publish(self, signal: SignalEnvelope, *, db: AsyncSession | None = None) -> SignalEnvelope:
        """Publish a signal after persisting it."""

    def subscribe(self, signal_type: str, handler: SignalHandler) -> None:
        """Register a handler for a specific signal type."""

    def subscribe_all(self, handler: SignalHandler) -> None:
        """Register a handler that receives every signal."""


class InProcessSignalPublisher:
    """Minimal signal publisher for the modular monolith."""

    def __init__(self, store: SignalStore) -> None:
        self._store = store
        self._typed_handlers: dict[str, list[SignalHandler]] = defaultdict(list)
        self._global_handlers: list[SignalHandler] = []

    def subscribe(self, signal_type: str, handler: SignalHandler) -> None:
        if handler not in self._typed_handlers[signal_type]:
            self._typed_handlers[signal_type].append(handler)

    def subscribe_all(self, handler: SignalHandler) -> None:
        if handler not in self._global_handlers:
            self._global_handlers.append(handler)

    async def publish(self, signal: SignalEnvelope, *, db: AsyncSession | None = None) -> SignalEnvelope:
        stored = await self._store.append(signal, db=db)
        handlers = [
            *self._global_handlers,
            *self._typed_handlers.get(signal.topic, []),
        ]
        for handler in handlers:
            try:
                await handler(stored)
            except Exception:
                logger.exception(
                    "Signal handler failed for topic=%s handler=%s",
                    signal.topic,
                    getattr(handler, "__name__", handler.__class__.__name__),
                )
        return stored
