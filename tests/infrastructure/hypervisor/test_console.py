"""Cas nominal et limite de console."""

import pytest

from app.application.ports.hypervisor import VmRef, VmSpec
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor


async def test_console_returns_a_url():
    """La console mockee expose une URL et une duree."""
    hypervisor = FakeHypervisor()
    ref = await hypervisor.create_vm(VmSpec("web", 1, 1, 1, 1))
    access = await hypervisor.console(ref)
    assert ref.vm_id in access.url
    assert access.expires_in == 300


async def test_console_unknown_vm():
    """Pas de console pour une VM absente."""
    hypervisor = FakeHypervisor()
    with pytest.raises(KeyError):
        await hypervisor.console(VmRef("nope"))
