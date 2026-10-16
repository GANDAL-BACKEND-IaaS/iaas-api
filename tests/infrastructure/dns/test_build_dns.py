"""Cas nominal et limite de build_dns."""

from app.infrastructure.dns.factory import DnsSettings, build_dns
from app.infrastructure.dns.fake_dns import FakeDns
from app.infrastructure.dns.http_dns import HttpDns


def test_fake_is_the_default():
    """Sans configuration, le mock est retourne."""
    assert isinstance(build_dns(DnsSettings(_env_file=None)), FakeDns)


def test_http_mode_returns_the_http_client():
    """DNS_MODE=http retourne le client HTTP configure."""
    dns = build_dns(DnsSettings(_env_file=None, mode="http", base_url="http://dns.test/",
                                token="t", attempts=3))
    assert isinstance(dns, HttpDns)


def test_settings_are_read_from_the_environment(monkeypatch):
    """Les variables DNS_* sont prises en compte."""
    monkeypatch.setenv("DNS_MODE", "http")
    monkeypatch.setenv("DNS_BASE_URL", "http://dns.env")
    settings = DnsSettings(_env_file=None)
    assert settings.mode == "http" and settings.base_url == "http://dns.env"
    assert isinstance(build_dns(settings), HttpDns)
