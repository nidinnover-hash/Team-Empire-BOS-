# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import logging

logger = logging.getLogger(__name__)

from app.models.approval import Approval
from app.models.event import Event
from app.models.integration import Integration
from app.models.registry import load_all_models


def _has_prefix_index(table, expected_cols: tuple[str, ...]) -> bool:
    # Single-column indexes declared via column.index=True
    if len(expected_cols) == 1:
        col = table.columns.get(expected_cols[0])
        if col is not None and bool(getattr(col, "index", False)):
            return True
    for idx in table.indexes:
        cols = tuple(col.name for col in idx.columns)
        if cols[: len(expected_cols)] == expected_cols:
            return True
    return False


def main() -> int:
    load_all_models()
    required: list[tuple[object, tuple[str, ...], str]] = [
        (Event.__table__, ("organization_id", "event_type", "created_at"), "events org/event/time scans"),
        (Approval.__table__, ("organization_id", "status", "created_at"), "approval queue scans"),
        (Integration.__table__, ("organization_id", "status", "last_sync_at"), "integration health scans"),
    ]
    missing: list[str] = []
    for table, cols, reason in required:
        if not _has_prefix_index(table, cols):
            missing.append(f"{table.name} missing index prefix {cols} ({reason})")
    if missing:
        logger.error("Critical index guard failed:")
        for row in missing:
            logger.error("- %s", row)
        return 1
    logger.info("Critical index guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
