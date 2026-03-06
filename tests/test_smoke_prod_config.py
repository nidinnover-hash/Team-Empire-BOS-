from __future__ import annotations

from scripts import smoke_prod_config


def test_require_supported_runtime_for_import_matches_current_runtime(monkeypatch):
    monkeypatch.setattr(smoke_prod_config.sys, "version_info", (3, 12, 5, "final", 0))
    assert smoke_prod_config._require_supported_runtime_for_import() == 0


def test_require_supported_runtime_for_import_rejects_other_versions(monkeypatch):
    monkeypatch.setattr(smoke_prod_config.sys, "version_info", (3, 14, 0, "final", 0))
    assert smoke_prod_config._require_supported_runtime_for_import() == 1
