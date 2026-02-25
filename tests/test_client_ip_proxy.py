from types import SimpleNamespace

from app.core.config import settings
from app.core.middleware import get_client_ip


def _req(direct_ip: str, xff: str | None = None):
    headers = {}
    if xff is not None:
        headers["X-Forwarded-For"] = xff
    return SimpleNamespace(client=SimpleNamespace(host=direct_ip), headers=headers)


def test_get_client_ip_prefers_direct_ip_when_forwarded_disabled(monkeypatch):
    monkeypatch.setattr(settings, "USE_FORWARDED_HEADERS", False)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    assert get_client_ip(_req("10.1.2.3", "1.2.3.4")) == "10.1.2.3"


def test_get_client_ip_uses_forwarded_for_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "USE_FORWARDED_HEADERS", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    assert get_client_ip(_req("10.1.2.3", "1.2.3.4, 5.6.7.8")) == "1.2.3.4"


def test_get_client_ip_ignores_forwarded_for_untrusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "USE_FORWARDED_HEADERS", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    assert get_client_ip(_req("203.0.113.5", "1.2.3.4")) == "203.0.113.5"
