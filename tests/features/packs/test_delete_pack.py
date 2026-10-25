"""Cas nominaux et limites de la suppression de pack (F17, R14)."""

from app.features.requests.service import submit_request
from app.shared.enums import RequestKind
from app.shared.models.packs import Pack
from tests.support import add_pack, login_header, own_project


async def test_delete_pack_blocked_by_pending_request(client, db, iam):
    """Un pack lie a une demande de creation en attente ne se supprime pas."""
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
    response = client.delete(f"/api/v1/admin/packs/{pack.id}", headers=headers)
    assert response.status_code == 409
    assert db.get(Pack, pack.id) is not None


async def test_delete_pack_when_unused(client, db, iam):
    """Un pack sans demande en attente est supprime."""
    pack = add_pack(db, "Libre", ram_gb=1, vcpu=1, vram_gb=1, ssd_gb=1)
    headers = await login_header(iam, "root@x.cm")
    response = client.delete(f"/api/v1/admin/packs/{pack.id}", headers=headers)
    assert response.status_code == 204
    assert db.get(Pack, pack.id) is None


def test_delete_pack_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.delete("/api/v1/admin/packs/1").status_code == 401
