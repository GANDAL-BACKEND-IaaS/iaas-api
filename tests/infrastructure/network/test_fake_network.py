"""Tests du mock FakeNetwork (comportement, idempotence, pannes, reset)."""

import pytest

from app.application.ports.hypervisor import VmRef
from app.application.ports.network import NetworkNotFound, NetworkRef, NetworkUnavailable
from app.infrastructure.network.fake_network import FakeNetwork


async def test_fake_network_create_and_delete():
    """Creation et suppression de reseau."""
    mock = FakeNetwork()
    ref = await mock.create_network("p1", "lan-1")
    assert ref.network_id in mock.networks
    assert mock.project_of[ref.network_id] == "p1"

    await mock.delete_network(ref)
    assert ref.network_id not in mock.networks
    assert ref.network_id not in mock.project_of

    # Idempotence de la suppression
    await mock.delete_network(ref)


async def test_fake_network_attach_and_detach_idempotence():
    """Rattachement et detachement d'une VM, rejouabilite."""
    mock = FakeNetwork()
    ref = await mock.create_network("p1", "lan-1")
    vm = VmRef("vm-1")

    await mock.attach_vm(ref, vm)
    assert (ref.network_id, "vm-1") in mock.links

    # Rattacher deux fois est idempotent
    await mock.attach_vm(ref, vm)
    assert len(mock.links) == 1

    await mock.detach_vm(ref, vm)
    assert (ref.network_id, "vm-1") not in mock.links

    # Detacher une VM absente est idempotent
    await mock.detach_vm(ref, vm)


async def test_fake_network_rejects_unknown_network():
    """Le mock leve NetworkNotFound si le reseau n'existe pas."""
    mock = FakeNetwork()
    unknown = NetworkRef("nonexistent-net")
    vm = VmRef("vm-1")

    with pytest.raises(NetworkNotFound):
        await mock.attach_vm(unknown, vm)

    with pytest.raises(NetworkNotFound):
        await mock.detach_vm(unknown, vm)


async def test_fake_network_failure_switch():
    """available=False bloque toute operation et leve NetworkUnavailable."""
    mock = FakeNetwork(available=False)
    with pytest.raises(NetworkUnavailable):
        await mock.create_network("p1", "lan-1")

    mock.available = True
    ref = await mock.create_network("p1", "lan-1")
    mock.available = False

    with pytest.raises(NetworkUnavailable):
        await mock.attach_vm(ref, VmRef("vm-1"))

    with pytest.raises(NetworkUnavailable):
        await mock.detach_vm(ref, VmRef("vm-1"))

    with pytest.raises(NetworkUnavailable):
        await mock.delete_network(ref)


async def test_fake_network_reset():
    """reset() nettoie l'etat en memoire et retablit la disponibilite."""
    mock = FakeNetwork(available=False)
    mock.networks["net-x"] = "temp"
    mock.links.add(("net-x", "vm-x"))
    mock.project_of["net-x"] = "p-x"

    mock.reset()
    assert mock.available is True
    assert not mock.networks
    assert not mock.links
    assert not mock.project_of


async def test_fake_network_delay():
    """Le delai est applique si delay_seconds > 0."""
    mock = FakeNetwork(delay_seconds=0.01)
    ref = await mock.create_network("p1", "lan-delay")
    assert ref.network_id


async def test_fake_network_toggle_script():
    """Verifie le bon fonctionnement du flag file utilise par toggle_network_failure.py."""
    from tests.infrastructure.network.toggle_network_failure import set_down, set_up, status

    mock = FakeNetwork()
    set_down()
    with pytest.raises(NetworkUnavailable):
        await mock.create_network("p1", "lan-down-flag")
    status()

    set_up()
    ref = await mock.create_network("p1", "lan-up-flag")
    assert ref.network_id
    mock.reset()
