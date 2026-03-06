"""Role-based visibility capabilities for sensitive UI/API data."""

from __future__ import annotations

SENSITIVE_FINANCIAL_ROLE_ORDER = ("CEO", "ADMIN", "MANAGER")
SENSITIVE_FINANCIAL_ROLES = set(SENSITIVE_FINANCIAL_ROLE_ORDER)

# Cross-company / multi-org rollup data: CEO-only by default.
CROSS_COMPANY_ROLE_ORDER = ("CEO",)
CROSS_COMPANY_ROLES = set(CROSS_COMPANY_ROLE_ORDER)

# CEO executive endpoints (status, playbook, board-packet): CEO + ADMIN.
CEO_EXECUTIVE_ROLE_ORDER = ("CEO", "ADMIN")
CEO_EXECUTIVE_ROLES = set(CEO_EXECUTIVE_ROLE_ORDER)


def normalize_role(role: object) -> str:
    return str(role or "").upper()


def can_view_sensitive_financials(role: object) -> bool:
    return normalize_role(role) in SENSITIVE_FINANCIAL_ROLES


def can_view_contact_financial_fields(role: object) -> bool:
    return can_view_sensitive_financials(role)


def can_view_contacts_pipeline_summary(role: object) -> bool:
    return can_view_sensitive_financials(role)


def can_view_cross_company(role: object) -> bool:
    """Only CEO can see cross-company rollup / multi-org dashboards."""
    return normalize_role(role) in CROSS_COMPANY_ROLES


def can_view_ceo_executive(role: object) -> bool:
    """CEO + ADMIN for executive cockpit data (board-packet, status, playbook)."""
    return normalize_role(role) in CEO_EXECUTIVE_ROLES
