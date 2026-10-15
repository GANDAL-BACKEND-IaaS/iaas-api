"""Parcours F8/F9 puis F15/F16 sur le moteur partage, avec les mocks Stockage et notifications."""

from sqlalchemy import select

from app.shared.models.storages import Storage


def _decide(api, headers, request_id, verb, note=None):
    body = {"note": note} if note is not None else {}
    return api.post(f"/api/v1/requests/{request_id}/{verb}", headers=headers, json=body)


async def test_accepted_creation_creates_the_storage_in_the_request_project(
    api, db, storage_port, notifications, world
):
    """F16 : acceptation, stockage cree dans le mock et rattache au projet de la demande."""
    request = api.post("/api/v1/projects/p2/storages", headers=world.owner,
                       json={"name": "photos", "size": 30}).json()
    accepted = _decide(api, world.admin, request["id"], "accept", "OK")
    assert accepted.status_code == 200 and accepted.json()["admin_note"] == "OK"
    storage = db.scalar(select(Storage).where(Storage.name == "photos"))
    assert storage.origin_project_id == "p2" and storage.size == 30
    assert storage.id in storage_port.spaces
    assert [n.user_id for n in notifications.sent] == [world.owner_id]


async def test_accepted_update_resizes_and_shared_view_follows(
    api, db, storage_port, notifications, world
):
    """F9 accepte : nouvelle taille en base et dans le mock, visible depuis le partage."""
    request = api.post("/api/v1/projects/p1/storages/st-1/update-requests",
                       headers=world.guest, json={"size": 80}).json()
    assert _decide(api, world.admin, request["id"], "accept").status_code == 200
    assert db.get(Storage, "st-1").size == 80 and storage_port.spaces["st-1"].size == 80
    shared = api.get("/api/v1/projects/p2/storages/st-1", headers=world.guest).json()
    assert shared["size"] == 80
    assert notifications.sent[0].user_id == world.guest_id


async def test_storage_group_down_keeps_the_request_pending(api, db, storage_port, world):
    """Port indisponible : 503 et la demande reste en attente, rien n'est cree."""
    request = api.post("/api/v1/projects/p1/storages", headers=world.owner,
                       json={"name": "logs", "size": 5}).json()
    storage_port.available = False
    response = _decide(api, world.admin, request["id"], "accept")
    assert response.status_code == 503
    status = api.get(f"/api/v1/requests/{request['id']}", headers=world.owner).json()["status"]
    assert status == "pending"
    assert db.scalar(select(Storage).where(Storage.name == "logs")) is None


async def test_refusal_cancellation_and_admin_only(api, storage_port, world):
    """Refus avec remarque sans appel au port ; annulation par l'auteur ; admin requis."""
    before = dict(storage_port.spaces)
    first = api.post("/api/v1/projects/p1/storages", headers=world.owner,
                     json={"name": "a", "size": 1}).json()
    assert _decide(api, world.owner, first["id"], "accept").status_code == 403
    refused = _decide(api, world.admin, first["id"], "refuse", "Quota atteint").json()
    assert (refused["status"], refused["admin_note"]) == ("refused", "Quota atteint")
    assert storage_port.spaces == before
    second = api.post("/api/v1/projects/p1/storages", headers=world.owner,
                      json={"name": "b", "size": 1}).json()
    assert api.post(f"/api/v1/requests/{second['id']}/cancel",
                    headers=world.guest).status_code == 403
    assert api.post(f"/api/v1/requests/{second['id']}/cancel",
                    headers=world.owner).json()["status"] == "cancelled"


async def test_update_of_deleted_storage_stays_pending(api, db, world):
    """Stockage supprime entre-temps : l'acceptation echoue et la demande reste en attente."""
    request = api.post("/api/v1/projects/p1/storages/st-1/update-requests",
                       headers=world.owner, json={"size": 90}).json()
    api.post("/api/v1/projects/p1/storages/st-1/deletion", headers=world.owner,
             json={"confirm": True})
    assert _decide(api, world.admin, request["id"], "accept").status_code == 404
    status = api.get(f"/api/v1/requests/{request['id']}", headers=world.owner).json()["status"]
    assert status == "pending"
    assert _decide(api, world.admin, request["id"], "refuse", "Supprime").status_code == 200
