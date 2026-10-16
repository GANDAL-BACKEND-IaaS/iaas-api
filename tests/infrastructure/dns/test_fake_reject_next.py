"""Cas nominal et limite de FakeDns.reject_next."""

import pytest

from app.application.ports.dns import DnsError, DnsRejected, DnsUnavailable
from app.infrastructure.dns.fake_dns import FakeDns


async def test_reject_next_refuses_without_recording():
    """Un refus definitif ne supprime rien et se distingue d'une indisponibilite."""
    dns = FakeDns()
    dns.reject_next()
    with pytest.raises(DnsRejected) as exc:
        await dns.delete_domain("vm-1")
    assert isinstance(exc.value, DnsError) and not isinstance(exc.value, DnsUnavailable)
    assert dns.deleted == []


async def test_reject_next_applies_once():
    """Le refus ne concerne que la demande programmee."""
    dns = FakeDns()
    dns.reject_next()
    with pytest.raises(DnsRejected):
        await dns.delete_domain("vm-1")
    await dns.delete_domain("vm-1")
    assert dns.deleted == ["vm-1"]
