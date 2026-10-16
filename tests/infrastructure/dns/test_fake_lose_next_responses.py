"""Cas nominal et limite de FakeDns.lose_next_responses."""

import pytest

from app.application.ports.dns import DnsUnavailable
from app.infrastructure.dns.fake_dns import FakeDns


async def test_lost_response_is_still_applied():
    """La demande est prise en compte meme si l'appelant recoit une erreur."""
    dns = FakeDns()
    dns.lose_next_responses()
    with pytest.raises(DnsUnavailable):
        await dns.delete_domain("vm-1")
    assert dns.deleted == ["vm-1"]


async def test_replay_after_lost_response_has_no_duplicate():
    """Rejouer apres une reponse perdue reussit sans doublon."""
    dns = FakeDns()
    dns.lose_next_responses()
    with pytest.raises(DnsUnavailable):
        await dns.delete_domain("vm-1")
    await dns.delete_domain("vm-1")
    assert dns.deleted == ["vm-1"]
    assert dns.received == {"vm-1": 2}
