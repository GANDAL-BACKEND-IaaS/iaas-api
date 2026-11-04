"""Cas nominaux et limites de la demande de modification de VM (F2)."""

from tests.support import add_vm, login_header, own_project


async def test_request_update_vm_is_pending(client, db, iam):
    """La modification depose une demande qui cible la VM."""
    await own_project(db, iam)
    add_vm(db, "p1")
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/update-requests",
        headers=headers,
        json={"configuration": {"ram_gb": 4, "vcpu": 2, "vram_gb": 0, "ssd_gb": 40}},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["kind"] == "vm_update"
    assert body["target_resource_id"] == "vm-1"
    assert body["status"] == "pending"


async def test_request_update_vm_unknown_is_not_found(client, db, iam):
    """Une VM absente ne peut pas etre modifiee."""
    await own_project(db, iam)
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms/missing/update-requests",
        headers=headers,
        json={"configuration": {"ram_gb": 2, "vcpu": 1, "vram_gb": 0, "ssd_gb": 10}},
    )
    assert response.status_code == 404


def test_request_update_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/update-requests",
        json={"configuration": {"ram_gb": 2, "vcpu": 1, "vram_gb": 0, "ssd_gb": 10}},
    )
    assert response.status_code == 401
