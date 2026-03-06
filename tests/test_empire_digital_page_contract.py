"""Contract checks for Empire Digital cockpit page role/fetch gating."""

from __future__ import annotations

from pathlib import Path

EMPIRE_PAGE_JS = Path("app/static/js/empire-digital-page.js")
SIDEBAR_HTML = Path("app/templates/partials/sidebar.html")


def _read(path: Path) -> str:
    if not path.exists():
        import pytest

        pytest.skip(f"{path} not found")
    return path.read_text(encoding="utf-8", errors="ignore")


def test_empire_page_uses_shared_role_caps_and_gates_routing_rule_fetch() -> None:
    js = _read(EMPIRE_PAGE_JS)
    assert "window.PCUI.loadRoleCapabilities" in js
    assert "canManageRouting" in js
    assert "if (!canAccessCockpit)" in js
    assert 'fetch("/api/v1/empire-digital/cockpit"' in js
    assert 'fetch("/api/v1/empire-digital/intelligence?limit=20"' in js
    assert 'fetch("/api/v1/empire-digital/leads" + params' in js
    assert 'fetch("/api/v1/empire-digital/leads/" + encodeURIComponent(String(leadId))' in js
    assert 'fetch("/api/v1/empire-digital/founder-report?window_days=7"' in js
    assert 'fetch("/api/v1/empire-digital/routing-rules?active_only=true"' in js
    assert '/api/v1/empire-digital/leads/export?format=' in js
    assert "if (!canManageRouting)" in js
    assert "Restricted. Empire CEO/Admin only." in js


def test_sidebar_exposes_empire_digital_nav_for_manager_tier() -> None:
    html = _read(SIDEBAR_HTML)
    assert "/web/empire-digital" in html
    assert "Empire Digital" in html
