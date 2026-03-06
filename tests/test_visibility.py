from app.core.visibility import (
    can_view_contact_financial_fields,
    can_view_contacts_pipeline_summary,
    can_view_sensitive_financials,
)


def test_sensitive_financial_visibility_role_matrix():
    assert can_view_sensitive_financials("CEO")
    assert can_view_sensitive_financials("admin")
    assert can_view_sensitive_financials("MANAGER")
    assert not can_view_sensitive_financials("STAFF")
    assert not can_view_sensitive_financials("EMPLOYEE")


def test_contacts_visibility_aligns_with_sensitive_financial_policy():
    assert can_view_contact_financial_fields("CEO")
    assert can_view_contacts_pipeline_summary("ADMIN")
    assert not can_view_contact_financial_fields("STAFF")
    assert not can_view_contacts_pipeline_summary("STAFF")
