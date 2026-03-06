"""Frontend contract tests for role-gated dashboard API calls."""

from __future__ import annotations

from pathlib import Path

DASHBOARD_JS = Path("app/static/js/dashboard-page.js")


def _read(path: Path) -> str:
    if not path.exists():
        import pytest

        pytest.skip(f"{path} not found")
    return path.read_text(encoding="utf-8", errors="ignore")


def test_dashboard_staff_role_gate_for_kpis_and_finance_calls() -> None:
    js = _read(DASHBOARD_JS)

    # KPI calls must be role-gated.
    assert "var canUseKpis = null;" in js
    assert "window.PCUI.loadRoleCapabilities" in js
    assert "if (!canUseKpis) return;" in js
    assert 'fetch("/api/v1/dashboard/kpis"' in js

    # Finance sparkline calls must be role-gated.
    assert "canUse = !!caps.canViewSensitiveFinancials;" in js
    assert "if (sparkHost && !sparkHost.querySelector(\"svg\") && canUse)" in js
    assert "Restricted" in js
    assert 'fetch("/api/v1/finance?limit=30"' in js
