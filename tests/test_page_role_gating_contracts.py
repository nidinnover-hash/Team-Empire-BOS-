"""Contract checks for page-level role gating to avoid hidden 403s."""

from __future__ import annotations

from pathlib import Path

CONTACTS_JS = Path("app/static/js/contacts-page.js")
DATA_HUB_JS = Path("app/static/js/data-hub-page.js")
HEALTH_JS = Path("app/static/js/health-page.js")
MEDIA_JS = Path("app/static/js/media-page.js")
TALK_JS = Path("app/static/js/talk-page.js")


def _read(path: Path) -> str:
    if not path.exists():
        import pytest

        pytest.skip(f"{path} not found")
    return path.read_text(encoding="utf-8", errors="ignore")


def test_contacts_pipeline_summary_is_role_gated() -> None:
    js = _read(CONTACTS_JS)
    assert "canViewPipeline" in js
    assert "canViewDealValues" in js
    assert "window.PCUI.loadRoleCapabilities" in js
    assert "if (!canViewPipeline)" in js
    assert 'fetch("/web/session")' in js
    assert 'fetch("/api/v1/contacts/pipeline-summary"' in js
    assert "canViewDealValues ? (c.deal_value ? formatCurrency(c.deal_value) : '--') : \"Restricted\"" in js
    assert "Restricted for your role" in js
    assert '"Restricted"' in js


def test_data_hub_sensitive_calls_are_role_gated() -> None:
    js = _read(DATA_HUB_JS)
    assert "canCollect" in js
    assert "canViewStorage" in js
    assert "canExport" in js
    assert "window.PCUI.loadRoleCapabilities" in js
    assert "caps.canCollectData" in js
    assert "caps.canViewStorage" in js
    assert "caps.canExportData" in js
    assert 'fetch("/web/session")' in js
    assert "Storage visibility is restricted to CEO/ADMIN." in js
    assert "Data collection is restricted to CEO/ADMIN/MANAGER." in js
    assert "Export is restricted to CEO role." in js


def test_health_token_calls_are_role_gated() -> None:
    js = _read(HEALTH_JS)
    assert "canManageTokens" in js
    assert "Token health is restricted to CEO/ADMIN." in js
    assert "Token rotation is restricted to CEO/ADMIN." in js


def test_media_write_actions_are_role_gated() -> None:
    js = _read(MEDIA_JS)
    assert "canManageMedia" in js
    assert "Upload is restricted to CEO/ADMIN" in js
    assert "View only" in js


def test_talk_forget_memory_is_role_gated() -> None:
    js = _read(TALK_JS)
    assert "canForgetLearned" in js
    assert "Memory management is restricted to CEO role." in js
