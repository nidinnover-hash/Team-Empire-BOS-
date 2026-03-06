"""Dead-letter queue — captures, inspects, and retries failed operations."""

from app.platform.dead_letter.inspector import count_by_status, get_entry, list_entries
from app.platform.dead_letter.reprocessor import archive_entry, archive_old_entries, retry_entry
from app.platform.dead_letter.store import capture_failure

__all__ = [
    "archive_entry",
    "archive_old_entries",
    "capture_failure",
    "count_by_status",
    "get_entry",
    "list_entries",
    "retry_entry",
]
