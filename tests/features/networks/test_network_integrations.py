"""Tests des fonctions d'integration internes destinees aux autres equipes."""

import pytest

from app.application.ports.hypervisor import VmRef
from app.core.errors import AppError
from app.features.networks import service
from app.shared.models.networks import Network, NetworkVm
from tests.support import add_project, add_vm


async def test_detach_vm_from_all_networks_integration(db, fake_network):
    """NAOMI - F6, R21 : suppression de VM retire la VM de tous les reseaux."""
    add_project(db, owner_id="u1", project_id="p1")
    add_project(db, owner_id="u1", project_id="p2")
    add_vm(db, project_id="p1", vm_id="vm-1")

    # Cree un reseau dans p1 et un dans p2
    ref1 = await fake_network.create_network("p1", "net-p1")
    ref2 = await fake_network.create_network("p2", "net-p2")
    db.add(Network(id=ref1.network_id, project_id="p1", name="net-p1"))
    db.add(Network(id=ref2.network_id, project_id="p2", name="net-p2"))

    # Attache vm-1 aux deux reseaux
    await fake_network.attach_vm(ref1, VmRef("vm-1"))
    await fake_network.attach_vm(ref2, VmRef("vm-1"))
    db.add(NetworkVm(network_id=ref1.network_id, vm_id="vm-1"))
    db.add(NetworkVm(network_id=ref2.network_id, vm_id="vm-1"))
    db.commit()

    # Appel de l'integration
    await service.detach_vm_from_all_networks(db, fake_network, vm_id="vm-1")

    # Verifie qu'elle n'est plus dans aucun reseau en base ni dans le mock
    assert (ref1.network_id, "vm-1") not in fake_network.links
    assert (ref2.network_id, "vm-1") not in fake_network.links
    assert db.get(NetworkVm, (ref1.network_id, "vm-1")) is None
    assert db.get(NetworkVm, (ref2.network_id, "vm-1")) is None

    # Rejouabilite sans erreur
    await service.detach_vm_from_all_networks(db, fake_network, vm_id="vm-1")


async def test_detach_vm_from_project_networks_integration(db, fake_network):
    """Socle shares - F14, R21 : retrait de partage ne retire la VM que du projet destinataire."""
    add_project(db, owner_id="u1", project_id="p1")
    add_project(db, owner_id="u1", project_id="p2")
    add_vm(db, project_id="p1", vm_id="vm-shared")

    ref1 = await fake_network.create_network("p1", "net-origin")
    ref2 = await fake_network.create_network("p2", "net-dest")
    db.add(Network(id=ref1.network_id, project_id="p1", name="net-origin"))
    db.add(Network(id=ref2.network_id, project_id="p2", name="net-dest"))

    await fake_network.attach_vm(ref1, VmRef("vm-shared"))
    await fake_network.attach_vm(ref2, VmRef("vm-shared"))
    db.add(NetworkVm(network_id=ref1.network_id, vm_id="vm-shared"))
    db.add(NetworkVm(network_id=ref2.network_id, vm_id="vm-shared"))
    db.commit()

    # Retrait du partage vers p2
    await service.detach_vm_from_project_networks(db, fake_network, vm_id="vm-shared", project_id="p2")

    # p2 est nettoye, p1 est conserve
    assert (ref2.network_id, "vm-shared") not in fake_network.links
    assert db.get(NetworkVm, (ref2.network_id, "vm-shared")) is None
    assert (ref1.network_id, "vm-shared") in fake_network.links
    assert db.get(NetworkVm, (ref1.network_id, "vm-shared")) is not None

    # Idempotence
    await service.detach_vm_from_project_networks(db, fake_network, vm_id="vm-shared", project_id="p2")


async def test_delete_project_networks_integration(db, fake_network):
    """ZUCHUON - F12, R23 : suppression de projet supprime tous ses reseaux."""
    add_project(db, owner_id="u1", project_id="p1")
    add_project(db, owner_id="u1", project_id="p2")

    r1 = await fake_network.create_network("p1", "net-1")
    r2 = await fake_network.create_network("p1", "net-2")
    r3 = await fake_network.create_network("p2", "net-other")

    db.add(Network(id=r1.network_id, project_id="p1", name="net-1"))
    db.add(Network(id=r2.network_id, project_id="p1", name="net-2"))
    db.add(Network(id=r3.network_id, project_id="p2", name="net-other"))
    db.commit()

    await service.delete_project_networks(db, fake_network, project_id="p1")

    # p1 networks are gone
    assert r1.network_id not in fake_network.networks
    assert r2.network_id not in fake_network.networks
    assert db.get(Network, r1.network_id) is None
    assert db.get(Network, r2.network_id) is None

    # p2 network is kept
    assert r3.network_id in fake_network.networks
    assert db.get(Network, r3.network_id) is not None

    # Idempotence
    await service.delete_project_networks(db, fake_network, project_id="p1")


async def test_list_vm_networks_integration(db, fake_network):
    """Permet de retrouver les reseaux d'une VM."""
    add_project(db, owner_id="u1", project_id="p1")
    add_vm(db, project_id="p1", vm_id="vm-finder")

    r1 = await fake_network.create_network("p1", "lan-a")
    r2 = await fake_network.create_network("p1", "lan-b")
    db.add(Network(id=r1.network_id, project_id="p1", name="lan-a"))
    db.add(Network(id=r2.network_id, project_id="p1", name="lan-b"))
    db.add(NetworkVm(network_id=r1.network_id, vm_id="vm-finder"))
    db.commit()

    nets = service.list_vm_networks(db, vm_id="vm-finder")
    assert len(nets) == 1
    assert nets[0].id == r1.network_id

    nets_filtered = service.list_vm_networks(db, vm_id="vm-finder", project_id="p2")
    assert len(nets_filtered) == 0


async def test_detach_vm_from_all_networks_upstream_unavailable(db, fake_network):
    """Panne port pendant detachement VM -> upstream_unavailable."""
    add_project(db, owner_id="u1", project_id="p1")
    add_vm(db, project_id="p1", vm_id="vm-fail")

    r1 = await fake_network.create_network("p1", "lan-f")
    db.add(Network(id=r1.network_id, project_id="p1", name="lan-f"))
    db.add(NetworkVm(network_id=r1.network_id, vm_id="vm-fail"))
    db.commit()

    fake_network.available = False
    with pytest.raises(AppError) as exc_info:
        await service.detach_vm_from_all_networks(db, fake_network, vm_id="vm-fail")
    assert exc_info.value.code == "upstream_unavailable"
