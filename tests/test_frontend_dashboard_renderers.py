"""Regression tests for dashboard frontend DOM render hardening."""

from __future__ import annotations

from pathlib import Path

DASHBOARD_JS = Path("app/static/js/dashboard-page.js")
DASHBOARD_HTML = Path("app/templates/dashboard.html")


def _read(path: Path) -> str:
    if not path.exists():
        import pytest

        pytest.skip(f"{path} not found")
    return path.read_text(encoding="utf-8", errors="ignore")


def test_dashboard_dynamic_lists_use_dom_rendering():
    content = _read(DASHBOARD_JS)

    expectations = [
        ("loadInbox", "emails.forEach(", "renderInboxItem"),
        ("loadApprovals", "items.forEach(", "renderApprovalItem"),
        ("loadAudit", "events.forEach(", "renderAuditRow"),
        ("loadMemory", "entries.forEach(", "renderMemoryItem"),
        ("loadTasks", "tasks.forEach(", "renderTaskItem"),
    ]
    for fn_name, iterator_marker, helper in expectations:
        assert f"async function {fn_name}()" in content
        assert iterator_marker in content, f"{fn_name} should iterate with forEach"
        assert helper in content, f"Missing helper {helper}"

    assert "events.map(" not in content
    assert "entries.map(" not in content
    assert "steps.map(" not in content


def test_dashboard_chat_append_avoids_wrap_innerhtml():
    content = _read(DASHBOARD_JS)
    assert "wrap.innerHTML" not in content, "wrap.innerHTML should not be used"
    assert "DOMParser()" in content, "Expected DOMParser-based chat parsing guard"


def test_dashboard_has_no_inline_handlers_in_js_or_template():
    js = _read(DASHBOARD_JS)
    html = _read(DASHBOARD_HTML)
    assert 'onclick="' not in js
    assert 'onchange="' not in js
    assert 'onclick="' not in html
    assert 'onchange="' not in html
