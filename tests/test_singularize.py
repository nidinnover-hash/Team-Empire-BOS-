"""Unit tests for _singularize in audit_middleware."""
from __future__ import annotations

import pytest

from app.core.audit_middleware import _singularize


@pytest.mark.parametrize(
    "plural,expected",
    [
        # Irregular plurals (explicit dictionary)
        ("dependencies", "dependency"),
        ("companies", "company"),
        ("activities", "activity"),
        ("opportunities", "opportunity"),
        ("categories", "category"),
        ("strategies", "strategy"),
        ("histories", "history"),
        ("entries", "entry"),
        ("policies", "policy"),
        ("frequencies", "frequency"),
        ("currencies", "currency"),
        ("territories", "territory"),
        ("priorities", "priority"),
        ("inventories", "inventory"),
        ("analyses", "analysis"),
        ("statuses", "status"),
        # -ies pattern (not in dict, but caught by rule)
        ("deliveries", "delivery"),
        ("queries", "query"),
        # -ses / -xes / -shes / -ches
        ("addresses", "address"),
        ("boxes", "box"),
        ("batches", "batch"),
        ("pushes", "push"),
        # Regular trailing "s"
        ("contacts", "contact"),
        ("deals", "deal"),
        ("tasks", "task"),
        ("goals", "goal"),
        ("projects", "project"),
        ("quotes", "quote"),
        ("funnels", "funnel"),
        ("bundles", "bundle"),
        ("splits", "split"),
        ("rollups", "rollup"),
        # Words ending in "ss" should NOT be stripped
        ("access", "access"),
        ("process", "process"),
        # Already singular
        ("deal", "deal"),
        ("task", "task"),
    ],
)
def test_singularize(plural: str, expected: str) -> None:
    assert _singularize(plural) == expected


@pytest.mark.parametrize(
    "method,path,expected",
    [
        ("POST", "/api/v1/deal-dependencies", "deal_dependency_created"),
        ("DELETE", "/api/v1/deal-dependencies/5", "deal_dependency_deleted"),
        ("PUT", "/api/v1/deal-dependencies/1/resolve", "deal_dependency_resolve"),
        ("POST", "/api/v1/conversion-funnels", "conversion_funnel_created"),
        ("POST", "/api/v1/product-bundles", "product_bundle_created"),
        ("POST", "/api/v1/territory-assignments", "territory_assignment_created"),
    ],
)
def test_derive_event_type_with_singularize(method: str, path: str, expected: str) -> None:
    from app.core.audit_middleware import _derive_event_type

    assert _derive_event_type(method, path) == expected
