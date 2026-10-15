"""Cas nominaux et limites de share_storage (F14, R15 a R20)."""

from app.shared.enums import StorageState
from app.shared.models.storages import Storage
from tests.support import own_project

URL = "/api/v1/projects/{}/storages/{}/shares"


def _share(api, headers, dest, project_id="p1", storage_id="st-1"):
    return api.post(URL.format(project_id, storage_id), headers=headers,
                    json={"dest_project_id": dest})


async def test_owner_shares_immediately_without_storage_call(api, db, iam, storage_port, world):
    """Partage actif aussitot, sans administrateur ni appel au groupe Stockage."""
    await own_project(db, iam, "p4")
    before = dict(storage_port.spaces)
    response = _share(api, world.owner, "p4")
    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["resource_type"], body["origin_project_id"]) == (
        "active", "storage", "p1")
    assert storage_port.spaces == before
    names = [i["name"] for i in api.get("/api/v1/projects/p4/storages",
                                        headers=world.owner).json()["items"]]
    assert names == ["backup"]


async def test_preconditions(api, db, world):
    """Doublon actif, meme projet : conflict. Hors origine : bad_request.
    Proprietaires differents : forbidden. En cours de suppression : invalid_state."""
    assert _share(api, world.owner, "p2").status_code == 409
    assert _share(api, world.owner, "p1").status_code == 409
    from_dest = _share(api, world.owner, "p1", project_id="p2")
    assert from_dest.status_code == 400
    assert from_dest.json()["error"]["details"] == {"origin_project_id": "p1"}
    other_owner = _share(api, world.owner, "p3")
    assert other_owner.status_code == 403
    assert "meme proprietaire" in other_owner.json()["error"]["message"]
    assert _share(api, world.owner, "inconnu").status_code == 404
    db.get(Storage, "st-2").state = StorageState.DELETING.value
    db.commit()
    deleting = _share(api, world.owner, "p1", project_id="p2", storage_id="st-2")
    assert deleting.status_code == 409 and deleting.json()["error"]["code"] == "invalid_state"


async def test_guest_needs_share_right_and_destination_membership(api, db, iam, world):
    """Sans storage.share : forbidden. Avec, mais hors du destinataire : forbidden."""
    assert _share(api, world.guest, "p2", storage_id="st-1").status_code == 403
    await own_project(db, iam, "p4")
    await iam.update_rights(world.guest_id, "p1", ["storage.view", "storage.share"])
    not_member = _share(api, world.guest, "p4")
    assert not_member.status_code == 403
    assert "destinataire" in not_member.json()["error"]["message"]
    revoke = api.post(f"/api/v1/shares/{world.share_id}/revoke", headers=world.owner)
    assert revoke.status_code == 200
    again = _share(api, world.guest, "p2")
    assert again.status_code == 201 and again.json()["id"] != world.share_id


async def test_revocation_by_creator_owner_or_nobody_else(api, iam, world):
    """Retrait par le createur ou le proprietaire ; un tiers est refuse."""
    await iam.update_rights(world.guest_id, "p1", ["storage.view", "storage.share"])
    api.post(f"/api/v1/shares/{world.share_id}/revoke", headers=world.owner)
    guest_share = _share(api, world.guest, "p2").json()["id"]
    assert api.post(f"/api/v1/shares/{guest_share}/revoke",
                    headers=world.other).status_code == 403
    assert api.post(f"/api/v1/shares/{guest_share}/revoke",
                    headers=world.guest).status_code == 200
    listing = api.get("/api/v1/projects/p2/storages", headers=world.guest).json()
    assert [i["name"] for i in listing["items"]] == ["media"]


async def test_missing_storage_and_token(api, world):
    """Stockage inconnu : not_found. Sans jeton : unauthorized."""
    assert _share(api, world.owner, "p2", storage_id="absent").status_code == 404
    response = api.post(URL.format("p1", "st-1"), json={"dest_project_id": "p2"})
    assert response.status_code == 401
