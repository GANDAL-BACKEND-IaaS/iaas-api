"""Cas nominal et limite de delete_domain."""

import pytest

from app.application.ports.dns import DnsUnavailable
from app.infrastructure.dns.fake_dns import FakeDns


async def test_delete_domain_is_idempotent():
    """Deux demandes pour la meme VM n'empilent pas de doublon."""
    dns = FakeDns()
    await dns.delete_domain("vm-1")
    await dns.delete_domain("vm-1")
    assert dns.deleted == ["vm-1"]


async def test_delete_domain_when_unavailable():
    """Une equipe DNS indisponible ne memorise rien."""
    dns = FakeDns(available=False)
    with pytest.raises(DnsUnavailable):
        await dns.delete_domain("vm-1")
    assert dns.deleted == []
