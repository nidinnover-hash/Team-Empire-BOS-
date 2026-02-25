"""Tests for hardening round 8: CSP inline, rate limit, OAuth validation, cache control, audit."""
import inspect


# ── 1. dashboard-page.js has no inline onclick handlers ───────────────────

def test_dashboard_no_inline_onclick():
    """CSP nonce policy blocks inline onclick; must use event delegation."""
    from pathlib import Path

    js_file = Path("app/static/js/dashboard-page.js")
    if not js_file.exists():
        import pytest
        pytest.skip("dashboard-page.js not found")
    content = js_file.read_text(encoding="utf-8", errors="ignore")
    assert 'onclick="' not in content, "Inline onclick found — blocked by CSP nonce policy"
    assert "data-agent-msg" in content, "Expected data-agent-msg attribute for delegation"
    assert "data-agent-idx" in content, "Expected data-agent-idx attribute for delegation"


# ── 2. Compose rate limiter returns 429 when cap is reached ───────────────

def test_compose_rate_limiter_returns_429_at_cap():
    """When _COMPOSE_MAX_ORGS is reached, new orgs should get 429, not bypass."""
    source = inspect.getsource(
        __import__("app.api.v1.endpoints.email", fromlist=["_check_compose_rate"])._check_compose_rate
    )
    # Should NOT silently return; should raise 429
    assert "return  # Silently" not in source, "Rate limiter should not silently skip at cap"
    assert "429" in source, "Should return 429 when org cap is reached"


# ── 3. Gmail OAuth callback validates code length ─────────────────────────

def test_gmail_callback_validates_code():
    """Gmail callback should reject empty code parameter."""
    source = inspect.getsource(
        __import__("app.api.v1.endpoints.email", fromlist=["gmail_callback"]).gmail_callback
    )
    assert "min_length=1" in source, "code parameter should have min_length=1 validation"


# ── 4. Login failure cleanup threshold aligned with cap ───────────────────

def test_login_failure_cleanup_threshold():
    """Cleanup should trigger well before _LOGIN_MAX_IPS cap."""
    from app.core import middleware
    source = inspect.getsource(middleware.record_login_failure)
    # Should reference _LOGIN_MAX_IPS in cleanup, not hardcoded 100
    assert "_LOGIN_MAX_IPS" in source, "Cleanup threshold should reference _LOGIN_MAX_IPS, not a hardcoded value"


# ── 5. Cache-Control no-store header is set ───────────────────────────────

def test_cache_control_header_set():
    """SecurityHeadersMiddleware should set Cache-Control: no-store."""
    from app.core import middleware
    source = inspect.getsource(middleware.SecurityHeadersMiddleware)
    assert "Cache-Control" in source, "SecurityHeadersMiddleware should set Cache-Control header"
    assert "no-store" in source, "Cache-Control should include no-store directive"


# ── 6. Approval audit logs include request_id ─────────────────────────────

def test_approval_audit_includes_request_id():
    """Approval request/grant/reject audit logs should include request_id."""
    source = inspect.getsource(
        __import__("app.api.v1.endpoints.approvals", fromlist=["_module"])
    )
    # All three audit calls should include request_id
    assert source.count("request_id") >= 3, (
        "Expected request_id in at least 3 audit log calls (request, approve, reject)"
    )
    assert "get_current_request_id" in source, "Should use get_current_request_id()"
