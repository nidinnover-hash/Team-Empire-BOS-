from urllib.parse import parse_qs

from app.core.middleware import sanitize_query_for_logs


def test_sanitize_query_for_logs_redacts_sensitive_keys():
    raw = (
        "hub.mode=subscribe&hub.verify_token=super-secret"
        "&hub.challenge=abc123&state=signedstate&page=2"
    )
    safe = sanitize_query_for_logs(raw)
    parsed = parse_qs(safe, keep_blank_values=True)

    assert parsed["hub.mode"] == ["subscribe"]
    assert parsed["hub.challenge"] == ["abc123"]
    assert parsed["page"] == ["2"]
    assert parsed["hub.verify_token"] == ["[REDACTED]"]
    assert parsed["state"] == ["[REDACTED]"]
