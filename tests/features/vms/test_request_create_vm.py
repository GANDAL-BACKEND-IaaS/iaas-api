"""Cas nominaux et limites de la demande de creation de VM (F1)."""

from tests.support import add_pack, login_header, own_project

_CUSTOM = {
    "name": "web",
    "configuration": {"ram_gb": 2, "vcpu": 2, "vram_gb": 1, "ssd_gb": 40},
}


async def test_request_create_vm_is_pending(client, db, iam):
    """La route depose une demande en attente, sans creer la VM."""
    await own_project(db, iam)
    headers = await login_header(iam)
    response = client.post("/api/v1/projects/p1/vms", headers=headers, json=_CUSTOM)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["kind"] == "vm_create"
    assert body["payload"]["configuration"]["ram_gb"] == 2


async def test_request_create_vm_rejects_pack_and_custom(client, db, iam):
    """Un pack et une configuration personnalisee ne se combinent pas."""
    await own_project(db, iam)
    pack = add_pack(db, "Standard", ram_gb=1, vcpu=1, vram_gb=1, ssd_gb=1)
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms",
        headers=headers,
        json={**_CUSTOM, "pack_id": pack.id},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_request_create_vm_forbidden_for_outsider(client, db, iam):
    """Un utilisateur qui n'est pas membre ne depose pas de demande."""
    await own_project(db, iam)
    iam.add_user("out@x.cm", "pw")
    headers = await login_header(iam, "out@x.cm")
    response = client.post("/api/v1/projects/p1/vms", headers=headers, json=_CUSTOM)
    assert response.status_code == 403


def test_request_create_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/vms", json=_CUSTOM)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
