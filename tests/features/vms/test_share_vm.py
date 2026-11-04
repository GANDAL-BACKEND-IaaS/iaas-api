"""Cas nominaux et limites du partage d'une VM (F14)."""

from tests.support import add_project, add_vm, login_header, own_project, user_id


async def test_share_vm_becomes_active(client, db, iam):
    """Le partage depuis le projet d'origine devient actif."""
    uid = await user_id(iam)
    await iam.create_project(uid, "p1")
    await iam.create_project(uid, "p2")
    add_project(db, uid, "p1")
    add_project(db, uid, "p2")
    add_vm(db, "p1")
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/shares",
        headers=headers,
        json={"dest_project_id": "p2"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "active"
    assert response.json()["dest_project_id"] == "p2"


async def test_share_vm_from_other_project_is_forbidden(client, db, iam):
    """On ne partage pas une VM depuis un projet qui n'est pas son origine."""
    await own_project(db, iam, "p1")
    await own_project(db, iam, "p2")
    add_vm(db, "p1")
    headers = await login_header(iam)
    response = client.post(
        "/api/v1/projects/p2/vms/vm-1/shares",
        headers=headers,
        json={"dest_project_id": "p1"},
    )
    assert response.status_code == 400


def test_share_vm_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post(
        "/api/v1/projects/p1/vms/vm-1/shares", json={"dest_project_id": "p2"}
    )
    assert response.status_code == 401
