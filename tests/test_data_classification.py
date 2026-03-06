"""Tests for the data classification engine."""
from app.core.data_classification import (
    RESTRICTED_MARKER,
    DataClassification,
    can_access_field,
    get_field_classification,
    get_role_clearance,
    sanitize_dict_for_role,
    sanitize_list_for_role,
)

# ── Classification enum ─────────────────────────────────────────────────────


def test_classification_ordering():
    assert DataClassification.PUBLIC < DataClassification.INTERNAL
    assert DataClassification.INTERNAL < DataClassification.CONFIDENTIAL
    assert DataClassification.CONFIDENTIAL < DataClassification.SECRET


# ── Role clearance ───────────────────────────────────────────────────────────


def test_ceo_has_secret_clearance():
    assert get_role_clearance("CEO") == DataClassification.SECRET


def test_admin_has_confidential_clearance():
    assert get_role_clearance("ADMIN") == DataClassification.CONFIDENTIAL


def test_manager_has_internal_clearance():
    assert get_role_clearance("MANAGER") == DataClassification.INTERNAL


def test_staff_has_public_clearance():
    assert get_role_clearance("STAFF") == DataClassification.PUBLIC


def test_viewer_has_public_clearance():
    assert get_role_clearance("VIEWER") == DataClassification.PUBLIC


def test_unknown_role_defaults_to_secret():
    assert get_role_clearance("UNKNOWN_ROLE") == DataClassification.SECRET


# ── Field classification ────────────────────────────────────────────────────


def test_contact_deal_value_is_confidential():
    assert get_field_classification("contacts", "deal_value") == DataClassification.CONFIDENTIAL


def test_contact_email_is_internal():
    assert get_field_classification("contacts", "email") == DataClassification.INTERNAL


def test_user_password_hash_is_secret():
    assert get_field_classification("users", "password_hash") == DataClassification.SECRET


def test_unknown_field_defaults_to_public():
    assert get_field_classification("contacts", "name") == DataClassification.PUBLIC


# ── can_access_field ─────────────────────────────────────────────────────────


def test_ceo_can_access_secret_field():
    assert can_access_field("CEO", "users", "password_hash") is True


def test_admin_cannot_access_secret_field():
    assert can_access_field("ADMIN", "users", "password_hash") is False


def test_admin_can_access_confidential_field():
    assert can_access_field("ADMIN", "contacts", "deal_value") is True


def test_manager_cannot_access_confidential_field():
    assert can_access_field("MANAGER", "contacts", "deal_value") is False


def test_manager_can_access_internal_field():
    assert can_access_field("MANAGER", "contacts", "email") is True


def test_staff_cannot_access_internal_field():
    assert can_access_field("STAFF", "contacts", "email") is False


def test_staff_can_access_public_field():
    assert can_access_field("STAFF", "contacts", "name") is True


# ── sanitize_dict_for_role ───────────────────────────────────────────────────


def test_ceo_sees_all_fields():
    data = {"name": "Acme", "deal_value": 50000, "phone": "+1234567890", "email": "a@b.com"}
    result = sanitize_dict_for_role(data, "contacts", "CEO")
    assert result == data


def test_staff_sees_only_public_fields():
    data = {"name": "Acme", "deal_value": 50000, "phone": "+1234567890", "email": "a@b.com"}
    result = sanitize_dict_for_role(data, "contacts", "STAFF")
    assert result["name"] == "Acme"
    assert result["deal_value"] is None  # numeric → None
    assert result["phone"] == RESTRICTED_MARKER
    assert result["email"] == RESTRICTED_MARKER


def test_manager_sees_internal_but_not_confidential():
    data = {"name": "Acme", "deal_value": 50000, "email": "a@b.com"}
    result = sanitize_dict_for_role(data, "contacts", "MANAGER")
    assert result["name"] == "Acme"
    assert result["deal_value"] is None
    assert result["email"] == "a@b.com"


def test_admin_sees_confidential_but_not_secret():
    data = {"password_hash": "secret123", "email": "a@b.com", "name": "Test"}
    result = sanitize_dict_for_role(data, "users", "ADMIN")
    assert result["name"] == "Test"
    assert result["email"] == "a@b.com"
    assert result["password_hash"] == RESTRICTED_MARKER


# ── sanitize_list_for_role ───────────────────────────────────────────────────


def test_sanitize_list_applies_to_all_items():
    data = [
        {"name": "A", "deal_value": 100},
        {"name": "B", "deal_value": 200},
    ]
    result = sanitize_list_for_role(data, "contacts", "STAFF")
    assert len(result) == 2
    assert result[0]["deal_value"] is None
    assert result[1]["deal_value"] is None
    assert result[0]["name"] == "A"
