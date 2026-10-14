"""Cas nominal et limite de delete_vm."""

from app.application.ports.hypervisor import VmRef, VmSpec
from app.infrastructure.hypervisor.fake_hypervisor import FakeHypervisor


async def test_delete_vm_is_replayable():
    """Supprimer deux fois la meme VM ne leve pas d'erreur."""
    hypervisor = FakeHypervisor()
    ref = await hypervisor.create_vm(VmSpec("web", 1, 1, 1, 1))
    await hypervisor.delete_vm(ref)
    await hypervisor.delete_vm(ref)
    await hypervisor.delete_vm(VmRef("absent"))
    assert hypervisor.vms == {}
