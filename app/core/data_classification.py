"""Data classification engine — field-level access control by role.

Every sensitive field is tagged with a classification level. Each role has a
clearance ceiling. Fields above a user's clearance are replaced with
``[RESTRICTED]`` in API responses.
"""
from __future__ import annotations

import enum


class DataClassification(enum.IntEnum):
    """Ordered sensitivity levels (higher = more restricted)."""
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    SECRET = 3


# ── Role → max clearance ────────────────────────────────────────────────────

ROLE_CLEARANCE: dict[str, DataClassification] = {
    "CEO": DataClassification.SECRET,
    "OWNER": DataClassification.SECRET,
    "ADMIN": DataClassification.CONFIDENTIAL,
    "TECH_LEAD": DataClassification.CONFIDENTIAL,
    "OPS_MANAGER": DataClassification.CONFIDENTIAL,
    "MANAGER": DataClassification.INTERNAL,
    "DEVELOPER": DataClassification.INTERNAL,
    "STAFF": DataClassification.PUBLIC,
    "EMPLOYEE": DataClassification.PUBLIC,
    "VIEWER": DataClassification.PUBLIC,
}

# ── (table, field) → classification ─────────────────────────────────────────

FIELD_CLASSIFICATIONS: dict[tuple[str, str], DataClassification] = {
    # Contacts
    ("contacts", "deal_value"): DataClassification.CONFIDENTIAL,
    ("contacts", "pipeline_stage"): DataClassification.CONFIDENTIAL,
    ("contacts", "phone"): DataClassification.CONFIDENTIAL,
    ("contacts", "email"): DataClassification.INTERNAL,
    ("contacts", "notes"): DataClassification.INTERNAL,
    # Finance
    ("finance_entries", "amount"): DataClassification.CONFIDENTIAL,
    ("finance_entries", "description"): DataClassification.INTERNAL,
    ("finance_entries", "category"): DataClassification.INTERNAL,
    # Users
    ("users", "password_hash"): DataClassification.SECRET,
    ("users", "totp_secret"): DataClassification.SECRET,
    ("users", "email"): DataClassification.INTERNAL,
    # Integrations
    ("integrations", "config_json"): DataClassification.SECRET,
    ("integrations", "access_token"): DataClassification.SECRET,
    ("integrations", "refresh_token"): DataClassification.SECRET,
    # API keys
    ("api_keys", "key_hash"): DataClassification.SECRET,
    # Emails
    ("emails", "body"): DataClassification.INTERNAL,
    ("emails", "from_address"): DataClassification.INTERNAL,
    ("emails", "to_address"): DataClassification.INTERNAL,
}

RESTRICTED_MARKER = "[RESTRICTED]"


def get_field_classification(table: str, field: str) -> DataClassification:
    return FIELD_CLASSIFICATIONS.get((table, field), DataClassification.PUBLIC)


def get_role_clearance(role: str) -> DataClassification:
    return ROLE_CLEARANCE.get(role, DataClassification.SECRET)


def can_access_field(role: str, table: str, field: str) -> bool:
    clearance = get_role_clearance(role)
    classification = get_field_classification(table, field)
    return clearance >= classification


def sanitize_dict_for_role(
    data: dict,
    table: str,
    role: str,
) -> dict:
    """Return a copy of *data* with fields above the role's clearance masked."""
    from app.core.config import settings
    if not settings.DATA_CLASSIFICATION_ENABLED:
        return data

    clearance = get_role_clearance(role)
    result = {}
    for key, value in data.items():
        classification = get_field_classification(table, key)
        if classification > clearance:
            if value is None or isinstance(value, int | float):
                result[key] = None
            else:
                result[key] = RESTRICTED_MARKER
        else:
            result[key] = value
    return result


def sanitize_list_for_role(
    data: list[dict],
    table: str,
    role: str,
) -> list[dict]:
    """Apply field sanitization to a list of dicts."""
    from app.core.config import settings
    if not settings.DATA_CLASSIFICATION_ENABLED:
        return data
    return [sanitize_dict_for_role(row, table, role) for row in data]
