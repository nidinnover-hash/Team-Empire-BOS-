import os
import json
from datetime import datetime
from typing import Any, List, Dict

LOG_FILE = os.path.join(os.path.dirname(__file__), "commands.json")


def _safe_read_json_list(path: str) -> List[Dict[str, Any]]:
    """Return a list from JSON file, or [] if file missing/empty/corrupt."""
    if not os.path.exists(path):
        return []

    try:
        # If file is empty, treat as []
        if os.path.getsize(path) == 0:
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, list) else []
    except Exception:
        return []


def _safe_write_json_list(path: str, data: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    if "role" in entry and "content" in entry:
        return entry
    text = str(entry.get("text", ""))
    return {
        "session_id": entry.get("session_id", "default"),
        "role": "user",
        "content": text,
        "time": entry.get("time", datetime.utcnow().isoformat()),
    }


def log_message(session_id: str, role: str, content: str) -> Dict[str, Any]:
    entry = {
        "session_id": session_id or "default",
        "role": role,
        "content": content,
        "time": datetime.utcnow().isoformat(),
    }
    data = get_memory()
    data.append(entry)
    _safe_write_json_list(LOG_FILE, data)
    return entry


def log_command(text: str) -> Dict[str, Any]:
    return log_message(session_id="default", role="user", content=text)


def get_memory() -> List[Dict[str, Any]]:
    raw = _safe_read_json_list(LOG_FILE)
    return [_normalize_entry(item) for item in raw if isinstance(item, dict)]


def get_session_memory(session_id: str) -> List[Dict[str, Any]]:
    sid = session_id or "default"
    return [item for item in get_memory() if item.get("session_id") == sid]


def clear_memory() -> None:
    _safe_write_json_list(LOG_FILE, [])


def clear_session_memory(session_id: str) -> int:
    sid = session_id or "default"
    data = get_memory()
    kept = [item for item in data if item.get("session_id") != sid]
    deleted = len(data) - len(kept)
    _safe_write_json_list(LOG_FILE, kept)
    return deleted
