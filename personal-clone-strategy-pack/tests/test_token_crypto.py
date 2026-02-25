from __future__ import annotations

from app.core import token_crypto


def test_encrypt_config_handles_already_encrypted_token() -> None:
    encrypted = token_crypto.encrypt_token("abc123")
    result = token_crypto.encrypt_config({"access_token": encrypted})
    assert isinstance(result["access_token"], str)
    assert result["access_token"].startswith("gAAAA")
    assert token_crypto.decrypt_token(result["access_token"]) == "abc123"


def test_decrypt_config_clears_invalid_fernet_token() -> None:
    malformed = "gAAAA-not-a-valid-fernet-token"
    result = token_crypto.decrypt_config({"access_token": malformed})
    assert result["access_token"] == ""
