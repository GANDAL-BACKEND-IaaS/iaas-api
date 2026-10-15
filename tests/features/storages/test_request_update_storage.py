"""Cas nominaux et limites de request_update_storage (F9)."""

from app.shared.enums import StorageState
from app.shared.models.storages import Storage

URL = "/api/v1/projects/{}/storages/{}/update-requests"


def _update(api, headers, project_id, storage_id, size):
    return api.post(URL.format(project_id, storage_id), headers=headers, json={"size": size})


async def test_guest_with_right_requests_a_new_size(api, db, world):
    """Invite avec storage.request_update : demande en attente, taille inchangee en base."""
    response = _update(api, world.guest, "p1", "st-1", 80)
    assert response.status_code == 202
    body = response.json()
    assert (body["kind"], body["status"], body["target_resource_id"]) == (
        "storage_update", "pending", "st-1")
    assert body["payload"] == {"size": 80}
    assert db.get(Storage, "st-1").size == 50


async def test_shared_storage_uses_destination_rights(api, world):
    """Dans p2, l'invite n'a que storage.view : il ne peut pas demander, meme sur st-1."""
    response = _update(api, world.guest, "p2", "st-1", 80)
    assert response.status_code == 403
    assert _update(api, world.owner, "p2", "st-1", 80).status_code == 202


async def test_same_size_duplicate_and_deleting(api, db, world):
    """Taille identique : bad_request. Seconde demande en attente : conflict.
    Stockage en cours de suppression : invalid_state."""
    same = _update(api, world.owner, "p1", "st-1", 50)
    assert same.status_code == 400 and same.json()["error"]["code"] == "bad_request"
    first = _update(api, world.owner, "p1", "st-1", 60).json()
    duplicate = _update(api, world.guest, "p1", "st-1", 70)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"] == {"request_id": first["id"]}
    db.get(Storage, "st-2").state = StorageState.DELETING.value
    db.commit()
    deleting = _update(api, world.owner, "p2", "st-2", 150)
    assert deleting.status_code == 409 and deleting.json()["error"]["code"] == "invalid_state"


async def test_new_request_allowed_once_previous_is_cancelled(api, world):
    """Apres annulation de la demande en attente, une nouvelle demande est acceptee."""
    first = _update(api, world.owner, "p1", "st-1", 60).json()
    cancel = api.post(f"/api/v1/requests/{first['id']}/cancel", headers=world.owner)
    assert cancel.status_code == 200
    assert _update(api, world.owner, "p1", "st-1", 70).status_code == 202


async def test_validation_visibility_and_membership(api, world):
    """Taille nulle : validation_error. Non visible : forbidden. Non-membre : forbidden."""
    assert _update(api, world.owner, "p1", "st-1", 0).status_code == 422
    assert _update(api, world.owner, "p1", "st-2", 150).status_code == 403
    assert _update(api, world.other, "p1", "st-1", 80).status_code == 403
    assert _update(api, world.owner, "p1", "absent", 80).status_code == 404
