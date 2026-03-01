"""Tests for hardening round 6: CSRF parsing, CSP inline, dead code, error sanitization."""
import inspect

import pytest

# ── 1. CSRF cookie parsing uses slice(1).join in all JS files ─────────────

def test_csrf_parsing_no_split_index_1():
    """All JS files must use split('=').slice(1).join('='), not split('=')[1]."""
    from pathlib import Path

    js_dir = Path("app/static/js")
    if not js_dir.exists():
        pytest.skip("JS static directory not found")

    violations = []
    for js_file in js_dir.glob("*.js"):
        content = js_file.read_text(encoding="utf-8", errors="ignore")
        if "split('=')[1]" in content or 'split("=")[1]' in content:
            violations.append(js_file.name)
    assert not violations, f"CSRF split('=')[1] still present in: {', '.join(violations)}"


# ── 2. ops-intel-page.js has no inline onclick handlers ───────────────────

def test_ops_intel_no_inline_onclick():
    """CSP nonce policy blocks inline onclick; must use event delegation."""
    from pathlib import Path

    js_file = Path("app/static/js/ops-intel-page.js")
    if not js_file.exists():
        pytest.skip("ops-intel-page.js not found")
    content = js_file.read_text(encoding="utf-8", errors="ignore")
    assert 'onclick="' not in content, "Inline onclick found — blocked by CSP nonce policy"
    assert "data-activate-policy" in content, "Expected data-activate-policy attribute for delegation"


# ── 3. data_collection RuntimeError does not leak internal message ────────

def test_data_collection_runtime_error_sanitized():
    """RuntimeError from OCR should return a safe message, not str(exc)."""
    source = inspect.getsource(
        __import__("app.api.v1.endpoints.data_collection", fromlist=["mobile_capture_upload_analyze"]).mobile_capture_upload_analyze
    )
    # Must have separate handlers for ValueError and RuntimeError
    assert "except RuntimeError" in source, "RuntimeError should be caught separately"
    assert '"Failed to extract text from image"' in source, "RuntimeError should return a safe fixed message"


# ── 4. _db_session_with_retry dead code is removed ───────────────────────

def test_db_session_with_retry_removed():
    """_db_session_with_retry should be removed from sync_scheduler."""
    from app.services import sync_scheduler
    assert not hasattr(sync_scheduler, "_db_session_with_retry"), (
        "_db_session_with_retry is dead code and should be removed"
    )


# ── 5. ops_intel.html includes ui-utils.js ───────────────────────────────

def test_ops_intel_includes_ui_utils():
    """ops_intel.html must load ui-utils.js for toast notifications."""
    from pathlib import Path

    html_file = Path("app/templates/ops_intel.html")
    if not html_file.exists():
        pytest.skip("ops_intel.html not found")
    content = html_file.read_text(encoding="utf-8", errors="ignore")
    assert "ui-utils.js" in content, "ops_intel.html should include ui-utils.js"


# ── 6. Dashboard /docs link opens in new tab ──────────────────────────────

def test_dashboard_docs_link_has_target_blank():
    """Dashboard /docs link must have target=_blank like all other pages."""
    from pathlib import Path

    # Sidebar may be inlined or in a partial include
    content = ""
    for candidate in [
        Path("app/templates/dashboard.html"),
        Path("app/templates/partials/sidebar.html"),
    ]:
        if candidate.exists():
            content += candidate.read_text(encoding="utf-8", errors="ignore")
    assert content, "dashboard.html and sidebar partial not found"
    # Find the /docs link and verify it has target="_blank"
    import re
    docs_links = re.findall(r'<a[^>]*href="/docs"[^>]*>', content)
    assert docs_links, "No /docs link found in dashboard or sidebar partial"
    for link in docs_links:
        assert 'target="_blank"' in link, f"/docs link missing target=_blank: {link}"


# ── 7. Social auto-publish audit does not hardcode actor_user_id=1 ───────

def test_social_publish_audit_no_hardcoded_user():
    """Scheduler auto-publish should not attribute to user 1."""
    source = inspect.getsource(
        __import__("app.services.sync_scheduler", fromlist=["_publish_due_social_posts"])._publish_due_social_posts
    )
    # The record_action call should use actor_user_id=None, not 1
    assert "actor_user_id=1" not in source, "Auto-publish audit should not hardcode actor_user_id=1"
    assert "actor_user_id=None" in source, "Auto-publish audit should use actor_user_id=None for scheduler actions"


# ── 8. Avatar memory migration is idempotent ─────────────────────────────

def test_avatar_memory_migration_idempotent():
    """Migration 0030 should check table existence before creating."""
    from pathlib import Path

    migration = Path("alembic/versions/20260224_0030_add_avatar_memory_table.py")
    if not migration.exists():
        pytest.skip("Migration file not found")
    content = migration.read_text(encoding="utf-8", errors="ignore")
    assert "get_table_names" in content or "IF NOT EXISTS" in content, (
        "Migration should check table existence before create_table"
    )
