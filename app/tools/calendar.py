from datetime import datetime


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_calendar_digest(payload: dict) -> dict:
    """
    Build a simple daily digest from payload events.
    Expected payload:
      {
        "date": "2026-02-21",
        "events": [
          {"title": "...", "start": "2026-02-21T09:00:00+00:00", "end": "..."},
        ]
      }
    """
    date_label = payload.get("date", "today")
    events = payload.get("events", [])

    normalized = []
    for item in events:
        title = item.get("title", "Untitled")
        start = _parse_dt(item.get("start"))
        end = _parse_dt(item.get("end"))
        duration_minutes = 0
        if start and end and end >= start:
            duration_minutes = int((end - start).total_seconds() // 60)
        normalized.append(
            {
                "title": title,
                "start": item.get("start"),
                "end": item.get("end"),
                "duration_minutes": duration_minutes,
            }
        )

    normalized.sort(key=lambda x: x.get("start") or "")
    total_events = len(normalized)
    total_minutes = sum(x["duration_minutes"] for x in normalized)
    summary = f"{total_events} events on {date_label} ({total_minutes} min planned)"

    return {
        "date": date_label,
        "total_events": total_events,
        "total_minutes": total_minutes,
        "events": normalized,
        "summary": summary,
    }
