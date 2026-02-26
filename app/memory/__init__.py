"""
app/memory — memory retrieval utilities for the AI agent.

The primary entry point is build_memory_context() in app/services/memory.py.
This package provides helpers for filtering and trimming memory context
to avoid flooding the AI with irrelevant or stale data.
"""

from app.memory.retrieval import (
    build_focused_context,
    filter_memory_by_category,
    trim_context_to_limit,
)

__all__ = [
    "build_focused_context",
    "filter_memory_by_category",
    "trim_context_to_limit",
]
