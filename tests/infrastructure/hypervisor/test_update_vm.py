"""Cas nominal et limite de update_vm."""

import pytest

from app.application.ports.hypervisor import VmRef, VmSpec
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor


async def test_update_vm_replaces_spec():
    """Les caracteristiques memorisees sont remplacees."""
    hypervisor = FakeHypervisor()
    ref = await hypervisor.create_vm(VmSpec("web", 1, 1, 1, 1))
    await hypervisor.update_vm(ref, VmSpec("web", 4, 2, 1, 8))
    assert hypervisor.vms[ref.vm_id].ram == 4


async def test_update_unknown_vm():
    """Une VM absente ne peut pas etre modifiee."""
    hypervisor = FakeHypervisor()
    with pytest.raises(KeyError):
        await hypervisor.update_vm(VmRef("nope"), VmSpec("web", 1, 1, 1, 1))
