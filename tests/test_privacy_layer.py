from app.core.config import settings
from app.core.privacy import REDACTED, sanitize_audit_payload
from app.logs import audit as audit_log


def test_sanitize_audit_payload_redacts_tokens_and_masks_pii():
    payload = {
        "access_token": "abc123",
        "refresh_token": "xyz",
        "authorization": "Bearer super-secret-token-value",
        "email": "founder@example.com",
        "to": "ops@example.com",
        "phone_number": "+1 (555) 123-4567",
        "ip": "192.168.1.100",
        "nested": {
            "client_secret": "dont-store-me",
            "note": "Contact me at ceo@example.com",
        },
        "reason": "approval_email_id_mismatch",
    }

    safe = sanitize_audit_payload(payload)

    assert safe["access_token"] == REDACTED
    assert safe["refresh_token"] == REDACTED
    assert safe["authorization"] == REDACTED
    assert safe["email"] == "f***@example.com"
    assert safe["to"] == "o***@example.com"
    assert safe["phone_number"].startswith("***")
    assert safe["ip"].endswith(".x")
    assert safe["nested"]["client_secret"] == REDACTED
    assert safe["nested"]["note"] == "Contact me at c***@example.com"
    assert safe["reason"] == "approval_email_id_mismatch"


async def test_record_action_applies_privacy_sanitizer(monkeypatch):
    captured = {}

    async def fake_log_event(db, data):
        captured["payload_json"] = data.payload_json
        return None

    monkeypatch.setattr(audit_log.event_service, "log_event", fake_log_event)

    await audit_log.record_action(
        db=None,  # not used by fake
        event_type="privacy_test",
        actor_user_id=1,
        organization_id=1,
        payload_json={
            "access_token": "should-hide",
            "email": "admin@example.com",
            "reason": "safe_reason",
        },
    )

    assert captured["payload_json"]["access_token"] == REDACTED
    assert captured["payload_json"]["email"] == "a***@example.com"
    assert captured["payload_json"]["reason"] == "safe_reason"


def test_privacy_profile_strict_masks_ip_in_free_text(monkeypatch):
    monkeypatch.setattr(settings, "PRIVACY_POLICY_PROFILE", "strict", raising=False)
    payload = {"note": "client ip 192.168.1.100 and email founder@example.com"}
    safe = sanitize_audit_payload(payload)
    assert "192.168.1.100" not in safe["note"]
    assert "founder@example.com" not in safe["note"]


def test_privacy_profile_debug_keeps_pii_but_redacts_secrets(monkeypatch):
    monkeypatch.setattr(settings, "PRIVACY_POLICY_PROFILE", "debug", raising=False)
    payload = {"email": "founder@example.com", "access_token": "top-secret"}
    safe = sanitize_audit_payload(payload)
    assert safe["email"] == "founder@example.com"
    assert safe["access_token"] == REDACTED
