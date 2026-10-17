"""Cas nominaux et limites de la suppression d'une VM (F6)."""

from app.shared.enums import ShareStatus
from app.shared.models.shares import ResourceShare
from app.shared.models.vms import Vm
from tests.support import add_project, add_vm, login_header, own_project, user_id


async def test_delete_vm_revokes_share_and_calls_dns(client, db, iam, dns):
    """La suppression revoque les partages et demande la suppression du nom de domaine."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    db.add(
        ResourceShare(
            resource_type="vm",
            resource_id="vm-1",
            origin_project_id="p1",
            dest_project_id="p2",
            created_by=uid,
            status=ShareStatus.ACTIVE.value,
        )
    )
    db.commit()
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/deletion", headers=headers, json={"confirm": True}
    )
    assert response.status_code == 204
    assert db.get(Vm, "vm-1") is None
    assert dns.deleted == ["vm-1"]
    share = db.query(ResourceShare).one()
    assert share.status == ShareStatus.REVOKED.value


async def test_delete_vm_dns_down_keeps_vm(client, db, iam, dns):
    """Si le DNS est indisponible, la VM reste en base."""
    await own_project(db, iam)
    add_vm(db, "p1")
    dns.available = False
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/deletion", headers=headers, json={"confirm": True}
    )
    assert response.status_code == 503
    assert db.get(Vm, "vm-1") is not None


def test_delete_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post("/api/v1/projects/p1/vms/vm-1/deletion", json={"confirm": True})
    assert response.status_code == 401
