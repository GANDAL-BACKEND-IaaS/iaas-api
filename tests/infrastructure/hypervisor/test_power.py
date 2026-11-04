"""Cas nominal et limite de power."""

import pytest

from app.application.ports.hypervisor import HypervisorUnavailable, VmRef, VmSpec
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor
from app.shared.enums import PowerAction


async def test_power_records_the_action():
    """L'action d'alimentation est journalisee par le mock."""
    hypervisor = FakeHypervisor()
    ref = await hypervisor.create_vm(VmSpec("web", 1, 1, 1, 1))
    await hypervisor.power(ref, PowerAction.START)
    assert hypervisor.power_log == [(ref.vm_id, PowerAction.START)]


async def test_power_unknown_or_down():
    """Une VM inconnue ou un hyperviseur coupe echoue."""
    hypervisor = FakeHypervisor()
    with pytest.raises(KeyError):
        await hypervisor.power(VmRef("nope"), PowerAction.STOP)
    hypervisor.available = False
    with pytest.raises(HypervisorUnavailable):
        await hypervisor.power(VmRef("nope"), PowerAction.STOP)
