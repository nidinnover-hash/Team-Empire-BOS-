"""Tests for the AI data minimization layer."""
from app.core.ai_privacy import PIIMasker

# ── Email masking ────────────────────────────────────────────────────────────


def test_masks_single_email():
    m = PIIMasker()
    result = m.mask("Contact john@example.com for info")
    assert "john@example.com" not in result
    assert "[EMAIL_1]" in result


def test_masks_multiple_emails():
    m = PIIMasker()
    result = m.mask("Send to alice@a.com and bob@b.com")
    assert "[EMAIL_1]" in result
    assert "[EMAIL_2]" in result
    assert "alice@a.com" not in result


def test_same_email_gets_same_placeholder():
    m = PIIMasker()
    result = m.mask("From john@x.com to john@x.com")
    assert result.count("[EMAIL_1]") == 2
    assert "[EMAIL_2]" not in result


# ── Phone masking ────────────────────────────────────────────────────────────


def test_masks_phone_number():
    m = PIIMasker()
    result = m.mask("Call +1-555-867-5309 now")
    assert "+1-555-867-5309" not in result
    assert "[PHONE_1]" in result


def test_masks_international_phone():
    m = PIIMasker()
    result = m.mask("Reach me at +91 98765 43210")
    assert "[PHONE_1]" in result


# ── SSN masking ──────────────────────────────────────────────────────────────


def test_masks_ssn():
    m = PIIMasker()
    result = m.mask("SSN is 123-45-6789")
    assert "123-45-6789" not in result
    assert "[SSN_1]" in result


# ── Credit card masking ──────────────────────────────────────────────────────


def test_masks_credit_card():
    m = PIIMasker()
    result = m.mask("Card: 4111 1111 1111 1111")
    assert "4111 1111 1111 1111" not in result
    assert "[CREDIT_CARD_1]" in result


def test_masks_credit_card_no_spaces():
    m = PIIMasker()
    result = m.mask("Card: 4111111111111111")
    assert "4111111111111111" not in result
    assert "[CREDIT_CARD_1]" in result


# ── Unmask ───────────────────────────────────────────────────────────────────


def test_unmask_restores_emails():
    m = PIIMasker()
    masked = m.mask("Email: john@example.com")
    restored = m.unmask(masked)
    assert "john@example.com" in restored


def test_unmask_restores_all_pii_types():
    m = PIIMasker()
    text = "Email john@x.com, SSN 123-45-6789, Card 4111111111111111"
    masked = m.mask(text)
    restored = m.unmask(masked)
    assert "john@x.com" in restored
    assert "123-45-6789" in restored
    assert "4111111111111111" in restored


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_empty_text_returns_empty():
    m = PIIMasker()
    assert m.mask("") == ""
    assert m.unmask("") == ""


def test_no_pii_text_unchanged():
    m = PIIMasker()
    text = "The quick brown fox jumps over the lazy dog"
    assert m.mask(text) == text


def test_unmask_on_no_pii_text_unchanged():
    m = PIIMasker()
    text = "Hello world"
    assert m.unmask(text) == text


# ── Allowed categories ──────────────────────────────────────────────────────


def test_allowed_email_not_masked():
    m = PIIMasker(allowed_categories={"email"})
    result = m.mask("Contact john@example.com")
    assert "john@example.com" in result
    assert "[EMAIL_1]" not in result


def test_allowed_phone_not_masked_but_email_is():
    m = PIIMasker(allowed_categories={"phone"})
    result = m.mask("john@x.com or +1-555-867-5309")
    assert "john@x.com" not in result
    assert "+1-555-867-5309" in result


# ── Summary ──────────────────────────────────────────────────────────────────


def test_pii_categories_found():
    m = PIIMasker()
    m.mask("Email john@x.com, SSN 123-45-6789")
    cats = m.pii_categories_found()
    assert "email" in cats
    assert "ssn" in cats


def test_total_masked_count():
    m = PIIMasker()
    m.mask("a@b.com and c@d.com and 123-45-6789")
    assert m.total_masked == 3


def test_summary_structure():
    m = PIIMasker()
    m.mask("a@b.com")
    s = m.summary()
    assert "categories" in s
    assert "total_masked" in s
    assert "counts" in s
    assert s["total_masked"] == 1
