"""Tests for hardening round 7: multi-tenant isolation, error sanitization, XSS, 404 messages."""
import inspect
import re

# ── 1. WhatsApp phone lookup has cache for performance ────────────────────

def test_whatsapp_phone_lookup_has_cache():
    """find_whatsapp_integration_by_phone_number_id should use a cache."""
    from app.services import integration as integration_mod
    assert hasattr(integration_mod, "_whatsapp_phone_cache"), (
        "WhatsApp phone lookup should have _whatsapp_phone_cache for performance"
    )
    assert isinstance(integration_mod._whatsapp_phone_cache, dict)


# ── 2. DigitalOcean sync does not leak upstream error details ─────────────

def test_digitalocean_sync_error_sanitized():
    """DO sync 400 should not expose str(error) to client."""
    from app.api.v1.endpoints import integrations_digitalocean
    source = inspect.getsource(integrations_digitalocean.digitalocean_sync)
    assert "detail=str(" not in source, "DigitalOcean sync should not use detail=str(...)"
    assert "Check your configuration" in source, "Should use a safe fixed message"


# ── 3. 404 messages do not expose entity IDs ──────────────────────────────

def test_404_messages_do_not_expose_ids():
    """404 detail messages should not include entity IDs (prevents enumeration)."""
    import importlib
    modules = [
        "app.api.v1.endpoints.tasks",
        "app.api.v1.endpoints.goals",
        "app.api.v1.endpoints.projects",
        "app.api.v1.endpoints.social",
        "app.api.v1.endpoints.ops",
    ]
    violations = []
    pattern = re.compile(r'detail=f".*\{.*_id\}.*not found"')
    for mod_name in modules:
        mod = importlib.import_module(mod_name)
        source = inspect.getsource(mod)
        matches = pattern.findall(source)
        for m in matches:
            violations.append(f"{mod_name}: {m}")
    assert not violations, "404 messages expose entity IDs:\n" + "\n".join(violations)


# ── 4. search-palette uses textContent for no-results message ─────────────

def test_search_palette_no_results_uses_textcontent():
    """search-palette.js should use textContent, not innerHTML, for the no-results message."""
    from pathlib import Path

    js_file = Path("app/static/js/search-palette.js")
    if not js_file.exists():
        import pytest
        pytest.skip("search-palette.js not found")
    content = js_file.read_text(encoding="utf-8", errors="ignore")
    # The no-results block should use textContent, not innerHTML with query
    assert "noResultEl.textContent" in content, "No-results message should use textContent"


# ── 5. email_service does not log raw exception messages ──────────────────

def test_email_service_does_not_log_raw_exceptions():
    """email_service.py should not log str(exc) for token persistence errors."""
    source = inspect.getsource(
        __import__("app.services.email_service", fromlist=["_module"])
    )
    # Should log type(exc).__name__, not the full exception
    assert 'type(exc).__name__' in source, "Should log exception type name, not full message"
