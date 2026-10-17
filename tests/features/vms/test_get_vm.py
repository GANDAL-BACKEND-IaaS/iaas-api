"""Cas nominaux et limites de la consultation d'une VM (F3)."""

from tests.support import add_vm, login_header, own_project


async def test_get_vm_returns_state(client, db, iam):
    """Le proprietaire consulte l'etat de sa VM."""
    await own_project(db, iam)
    add_vm(db, "p1")
    headers = await login_header(iam)
    response = client.get("/api/v1/projects/p1/vms/vm-1", headers=headers)
    assert response.status_code == 200
    assert response.json()["state"] == "stopped"
    assert response.json()["shared"] is False


async def test_get_vm_hidden_in_other_project(client, db, iam):
    """Une VM non visible dans le projet consulte est introuvable."""
    await own_project(db, iam, "p1")
    await own_project(db, iam, "p2")
    add_vm(db, "p1")
    headers = await login_header(iam)
    response = client.get("/api/v1/projects/p2/vms/vm-1", headers=headers)
    assert response.status_code == 404


def test_get_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1/vms/vm-1").status_code == 401
