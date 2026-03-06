"""Contract checks ensuring shared PCUI role capabilities are used on sensitive pages."""

from __future__ import annotations

from pathlib import Path

INTEGRATIONS_JS = Path("app/static/js/integrations-page.js")
SECURITY_JS = Path("app/static/js/security-page.js")
UI_UTILS_JS = Path("app/static/js/ui-utils.js")


def _read(path: Path) -> str:
    if not path.exists():
        import pytest

        pytest.skip(f"{path} not found")
    return path.read_text(encoding="utf-8", errors="ignore")


def test_ui_utils_exposes_role_capabilities_loader() -> None:
    js = _read(UI_UTILS_JS)
    assert "function _buildRoleCapabilities(user)" in js
    assert "canAccessEmpireCockpit" in js
    assert "canManageEmpireRouting" in js
    assert "canReviewEmpireIntelligence" in js
    assert "async function loadRoleCapabilities()" in js
    assert "loadRoleCapabilities: loadRoleCapabilities" in js


def test_integrations_page_uses_shared_role_capabilities() -> None:
    js = _read(INTEGRATIONS_JS)
    assert "window.PCUI.loadRoleCapabilities" in js
    assert "caps.canManageIntegrations" in js
    assert "Integrations access is restricted for your role." in js


def test_security_page_uses_shared_role_capabilities() -> None:
    js = _read(SECURITY_JS)
    assert "window.PCUI.loadRoleCapabilities" in js
    assert "caps.canManageSecurity" in js
    assert "Security controls are restricted for your role." in js
