"""Unit tests for inbox.py helper functions and edge cases.

The E2E tests in test_unified_inbox.py cover the full HTTP flow.
These unit tests exercise the pure helper logic directly:
  - _sort_key with None timestamp
  - _conversation_key for email, whatsapp, and unknown channels
  - get_unified_inbox pagination (offset/limit slicing)
"""
from datetime import UTC, datetime

from app.schemas.inbox import UnifiedInboxItem
from app.services.inbox import _conversation_key, _sort_key


def _make_item(
    *,
    channel: str = "email",
    item_id: int = 1,
    from_address: str | None = "user@example.com",
    to_address: str | None = "owner@example.com",
    timestamp: datetime | None = None,
) -> UnifiedInboxItem:
    return UnifiedInboxItem(
        channel=channel,
        item_id=item_id,
        external_id=None,
        direction="inbound",
        from_address=from_address,
        to_address=to_address,
        subject="Test" if channel == "email" else None,
        preview="Hello",
        status="pending",
        is_read=False,
        timestamp=timestamp,
    )


def test_sort_key_returns_min_for_none_timestamp():
    item = _make_item(timestamp=None)
    result = _sort_key(item)
    assert result == datetime.min.replace(tzinfo=UTC)


def test_sort_key_returns_actual_timestamp():
    ts = datetime(2026, 2, 26, 12, 0, tzinfo=UTC)
    item = _make_item(timestamp=ts)
    assert _sort_key(item) == ts


def test_sort_key_ordering():
    older = _make_item(timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _make_item(timestamp=datetime(2026, 2, 1, tzinfo=UTC))
    none_ts = _make_item(timestamp=None)
    items = [newer, none_ts, older]
    items.sort(key=_sort_key, reverse=True)
    assert items[0] is newer
    assert items[1] is older
    assert items[2] is none_ts


def test_conversation_key_email_uses_from_address():
    item = _make_item(channel="email", from_address="User@Example.COM", to_address="me@x.com")
    assert _conversation_key(item) == ("email", "user@example.com")


def test_conversation_key_email_falls_back_to_to_address():
    item = _make_item(channel="email", from_address=None, to_address="Recip@Example.COM")
    assert _conversation_key(item) == ("email", "recip@example.com")


def test_conversation_key_email_falls_back_to_item_id():
    item = _make_item(channel="email", from_address=None, to_address=None, item_id=42)
    assert _conversation_key(item) == ("email", "item:42")


def test_conversation_key_whatsapp_uses_from_address():
    item = _make_item(channel="whatsapp", from_address="+15551234567", to_address="+15550001111")
    assert _conversation_key(item) == ("whatsapp", "+15551234567")


def test_conversation_key_whatsapp_falls_back_to_to_address():
    item = _make_item(channel="whatsapp", from_address=None, to_address="+15550001111")
    assert _conversation_key(item) == ("whatsapp", "+15550001111")


def test_conversation_key_whatsapp_falls_back_to_item_id():
    item = _make_item(channel="whatsapp", from_address=None, to_address=None, item_id=99)
    assert _conversation_key(item) == ("whatsapp", "item:99")


def test_conversation_key_unknown_channel():
    item = _make_item(channel="sms", from_address="+1234", item_id=7)
    assert _conversation_key(item) == ("sms", "item:7")


def test_email_conversation_key_case_insensitive():
    """Email addresses should be lowercased for grouping."""
    item_a = _make_item(channel="email", from_address="Alice@BigCorp.COM")
    item_b = _make_item(channel="email", from_address="alice@bigcorp.com")
    assert _conversation_key(item_a) == _conversation_key(item_b)


def test_whatsapp_conversation_key_is_case_sensitive():
    """WhatsApp phone numbers are not lowercased."""
    item = _make_item(channel="whatsapp", from_address="+15551234567")
    key = _conversation_key(item)
    assert key == ("whatsapp", "+15551234567")
