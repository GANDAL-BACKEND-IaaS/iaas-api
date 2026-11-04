"""Cas nominaux et limites de la console d'une VM (F5)."""

from app.application.ports.hypervisor import VmSpec
from tests.support import add_vm, login_header, own_project


async def test_console_vm_returns_url(client, db, iam, hypervisor):
    """La console renvoie l'URL fournie par le port, sans ouvrir de session."""
    await own_project(db, iam)
    add_vm(db, "p1")
    hypervisor.vms["vm-1"] = VmSpec("web", 1, 1, 1, 1)
    headers = await login_header(iam)
    response = client.post("/api/v1/projects/p1/vms/vm-1/console", headers=headers)
    assert response.status_code == 200
    assert "vm-1" in response.json()["url"]
    assert response.json()["expires_in"] == 300


async def test_console_vm_unavailable(client, db, iam, hypervisor):
    """Un hyperviseur coupe refuse l'acces."""
    await own_project(db, iam)
    add_vm(db, "p1")
    hypervisor.available = False
    headers = await login_header(iam)
    response = client.post("/api/v1/projects/p1/vms/vm-1/console", headers=headers)
    assert response.status_code == 503


def test_console_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/projects/p1/vms/vm-1/console").status_code == 401
