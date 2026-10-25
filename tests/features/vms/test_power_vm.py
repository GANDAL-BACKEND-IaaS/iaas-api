"""Cas nominaux et limites de l'alimentation d'une VM (F4)."""

from app.application.ports.hypervisor import VmSpec
from tests.support import add_vm, login_header, own_project


def _register(hypervisor, vm_id="vm-1"):
    hypervisor.vms[vm_id] = VmSpec("web", 2, 2, 1, 40)


async def test_power_vm_starts_when_stopped(client, db, iam, hypervisor):
    """Demarrer une VM arretee la passe a running."""
    await own_project(db, iam)
    add_vm(db, "p1")
    _register(hypervisor)
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/power", headers=headers, json={"action": "start"}
    )
    assert response.status_code == 202
    assert response.json()["state"] == "starting"
    assert hypervisor.power_log[0][0] == "vm-1"
    assert hypervisor.power_log[0][1].value == "start"


async def test_power_vm_rejects_restart_when_stopped(client, db, iam, hypervisor):
    """Redemarrer une VM arretee est un etat invalide, sans appel effectif."""
    await own_project(db, iam)
    add_vm(db, "p1")
    _register(hypervisor)
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/power", headers=headers, json={"action": "restart"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"
    assert hypervisor.power_log == []


async def test_power_vm_upstream_does_not_change_state(client, db, iam, hypervisor):
    """Un hyperviseur indisponible laisse l'etat inchange."""
    await own_project(db, iam)
    add_vm(db, "p1")
    _register(hypervisor)
    hypervisor.available = False
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/power", headers=headers, json={"action": "start"}
    )
    assert response.status_code == 503
    follow = client.get("/api/v1/projects/p1/vms/vm-1", headers=headers)
    assert follow.json()["state"] == "stopped"


def test_power_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/vms/vm-1/power", json={"action": "start"})
    assert response.status_code == 401
