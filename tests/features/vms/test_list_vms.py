"""Cas nominaux et limites de la liste des VMs (F3)."""

from app.shared.enums import ShareStatus
from app.shared.models.shares import ResourceShare
from tests.support import add_project, add_vm, login_header, own_project, user_id


async def test_list_vms_includes_shared(client, db, iam):
    """Le projet destinataire voit la VM partagee, marquee shared."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1", "vm-1")
    add_vm(db, "p2", "vm-2", name="locale")
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
    response = client.get("/api/v1/projects/p2/vms", headers=headers)
    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}
    assert items["vm-1"]["shared"] is True
    assert items["vm-2"]["shared"] is False
    assert response.json()["total"] == 2


async def test_list_vms_forbidden_without_right(client, db, iam):
    """Un invite sans vm.view ne liste pas les VMs."""
    await own_project(db, iam)
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, "p1", ["storage.view"])
    headers = await login_header(iam, "guest@x.cm")
    response = client.get("/api/v1/projects/p1/vms", headers=headers)
    assert response.status_code == 403


def test_list_vms_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1/vms").status_code == 401
