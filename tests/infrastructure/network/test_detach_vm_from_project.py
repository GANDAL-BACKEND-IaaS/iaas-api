"""Cas nominal et limite de detach_vm_from_project."""

import pytest

from app.application.ports.hypervisor import VmRef
from app.application.ports.network import NetworkUnavailable
from app.infrastructure.network.fake_network import FakeNetwork


async def test_detach_vm_from_project_keeps_other_projects():
    """Seuls les liens du projet demande sont retires."""
    network = FakeNetwork()
    first = await network.create_network("p1", "a")
    second = await network.create_network("p2", "b")
    vm = VmRef("vm-1")
    await network.attach_vm(first, vm)
    await network.attach_vm(second, vm)
    await network.detach_vm_from_project(vm, "p1")
    assert (first.network_id, "vm-1") not in network.links
    assert (second.network_id, "vm-1") in network.links


async def test_detach_when_network_is_down():
    """Une panne reseau n'efface pas les liens."""
    network = FakeNetwork()
    ref = await network.create_network("p1", "a")
    await network.attach_vm(ref, VmRef("vm-1"))
    network.available = False
    with pytest.raises(NetworkUnavailable):
        await network.detach_vm_from_project(VmRef("vm-1"), "p1")
    assert network.links
