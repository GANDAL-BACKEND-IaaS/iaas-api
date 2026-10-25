"""Cas nominaux et limites de la modification de pack (F17, R14)."""

from app.features.requests.service import submit_request
from app.shared.enums import RequestKind
from app.shared.models.requests import ResourceRequest
from tests.support import add_pack, login_header, own_project


async def test_update_pack_refreshes_pending_request(client, db, iam):
    """Modifier un pack met a jour la demande de creation encore en attente."""
    uid = await own_project(db, iam)
    pack = add_pack(db, "Standard", ram_gb=1, vcpu=1, vram_gb=1, ssd_gb=1)
    await submit_request(
        db,
        iam,
        author_id=uid,
        project_id="p1",
        kind=RequestKind.VM_CREATE,
        payload={"name": "web", "pack_id": pack.id},
        target_resource_id=None,
    )
    headers = await login_header(iam, "root@x.cm")
    response = client.patch(
        f"/api/v1/admin/packs/{pack.id}", headers=headers, json={"ram_gb": 8}
    )
    assert response.status_code == 200
    stored = db.query(ResourceRequest).one()
    assert stored.payload["ram_gb"] == 8
    assert stored.status == "pending"


async def test_update_pack_unknown(client, iam):
    """Un pack absent est introuvable."""
    headers = await login_header(iam, "root@x.cm")
    response = client.patch("/api/v1/admin/packs/999", headers=headers, json={"ram_gb": 2})
    assert response.status_code == 404


def test_update_pack_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.patch("/api/v1/admin/packs/1", json={"ram": 2}).status_code == 401
