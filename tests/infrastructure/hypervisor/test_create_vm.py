"""Cas nominal et indisponibilite de create_vm."""

import pytest

from app.application.ports.hypervisor import HypervisorUnavailable, VmSpec
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor


async def test_create_vm_returns_a_ref():
    """Le mock cree une VM et la memorise."""
    hypervisor = FakeHypervisor()
    ref = await hypervisor.create_vm(VmSpec("web", 1, 1, 1, 1))
    assert ref.vm_id in hypervisor.vms


async def test_create_vm_when_unavailable():
    """Une panne n'enregistre rien."""
    hypervisor = FakeHypervisor(available=False)
    with pytest.raises(HypervisorUnavailable):
        await hypervisor.create_vm(VmSpec("web", 1, 1, 1, 1))
    assert hypervisor.vms == {}
