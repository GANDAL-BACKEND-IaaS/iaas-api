"""Cas nominal et limite de FakeDns.fail_next."""

import pytest

from app.application.ports.dns import DnsUnavailable
from app.infrastructure.dns.fake_dns import FakeDns


async def test_fail_next_counts_down_then_recovers():
    """Seules les demandes programmees echouent, la suivante passe."""
    dns = FakeDns()
    dns.fail_next(2)
    for _ in range(2):
        with pytest.raises(DnsUnavailable):
            await dns.delete_domain("vm-1")
    assert dns.received == {}
    await dns.delete_domain("vm-1")
    assert dns.deleted == ["vm-1"]


async def test_fail_next_zero_changes_nothing():
    """Programmer zero echec n'affecte pas la demande suivante."""
    dns = FakeDns()
    dns.fail_next(0)
    await dns.delete_domain("vm-1")
    assert dns.deleted == ["vm-1"]
