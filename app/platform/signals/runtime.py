"""Shared runtime accessors for the in-process signal backbone."""

from app.platform.signals.publisher import InProcessSignalPublisher
from app.platform.signals.store import InMemorySignalStore, SqlAlchemySignalStore

_signal_store = InMemorySignalStore()
_persistent_signal_store = SqlAlchemySignalStore()
_signal_publisher = InProcessSignalPublisher(_signal_store)


def get_signal_store() -> InMemorySignalStore:
    """Return the process-local signal store used during early refactors."""
    return _signal_store


def get_persistent_signal_store() -> SqlAlchemySignalStore:
    """Return the official persistent signal store."""
    return _persistent_signal_store


def get_signal_publisher() -> InProcessSignalPublisher:
    """Return the process-local signal publisher used during early refactors."""
    return _signal_publisher
