"""Tests for centralized mutation audit coverage contract."""
from __future__ import annotations

import pytest

from app.core.audit_middleware import (
    MutationAuditMiddleware,
    _derive_event_type,
    _extract_entity_id,
    _SKIP_PREFIXES,
)
from fastapi.routing import APIRoute
from app.main import app as fastapi_app


def test_derive_event_type_post():
    assert _derive_event_type("POST", "/api/v1/quotes") == "quote_created"


def test_derive_event_type_put():
    assert _derive_event_type("PUT", "/api/v1/quotes/5") == "quote_updated"


def test_derive_event_type_delete():
    assert _derive_event_type("DELETE", "/api/v1/quotes/5") == "quote_deleted"


def test_derive_event_type_nested_action():
    result = _derive_event_type("PUT", "/api/v1/deal-dependencies/1/resolve")
    assert result == "deal_dependencie_resolve"


def test_derive_event_type_hyphenated_resource():
    result = _derive_event_type("POST", "/api/v1/product-bundles")
    assert result == "product_bundle_created"


def test_extract_entity_id_with_id():
    assert _extract_entity_id("/api/v1/quotes/42") == 42


def test_extract_entity_id_nested():
    assert _extract_entity_id("/api/v1/product-bundles/7/items") == 7


def test_extract_entity_id_no_id():
    assert _extract_entity_id("/api/v1/quotes") is None


def test_skip_prefixes_cover_explicit_audit_endpoints():
    """Endpoints with explicit record_action should be in _SKIP_PREFIXES."""
    known_explicit = [
        "/api/v1/admin", "/api/v1/agents", "/api/v1/approvals",
        "/api/v1/quotes", "/api/v1/playbooks", "/api/v1/surveys",
    ]
    for prefix in known_explicit:
        assert any(prefix.startswith(skip) for skip in _SKIP_PREFIXES), \
            f"Endpoint with explicit audit not in skip list: {prefix}"


def test_batch15_20_mutation_routes_are_covered():
    """Every POST/PUT/PATCH/DELETE route in batches 15-20 should be either
    in _SKIP_PREFIXES (explicit audit) or covered by the middleware."""
    batch_prefixes = [
        "/api/v1/call-logs", "/api/v1/drip-analytics", "/api/v1/deal-splits",
        "/api/v1/contact-merge-logs", "/api/v1/product-bundles",
        "/api/v1/forecast-rollups", "/api/v1/conversion-funnels",
        "/api/v1/revenue-goals", "/api/v1/deal-dependencies",
        "/api/v1/contact-timeline", "/api/v1/email-warmup",
        "/api/v1/territory-assignments", "/api/v1/quote-approvals",
        "/api/v1/win-loss",
    ]
    for prefix in batch_prefixes:
        # Not in skip list = middleware covers it
        skipped = any(prefix.startswith(skip) for skip in _SKIP_PREFIXES)
        assert not skipped, \
            f"Batch 15-20 route {prefix} is in skip list — should be covered by middleware"


def test_middleware_class_exists():
    assert MutationAuditMiddleware is not None


def test_middleware_registered_in_app():
    """MutationAuditMiddleware should be in the app middleware stack."""
    middleware_classes = []
    for m in fastapi_app.user_middleware:
        middleware_classes.append(m.cls.__name__ if hasattr(m, "cls") else str(m))
    assert "MutationAuditMiddleware" in middleware_classes
