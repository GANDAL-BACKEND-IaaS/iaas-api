"""Cas nominaux et limites de list_storage_shares."""

from tests.support import own_project

URL = "/api/v1/projects/{}/storages/{}/shares"


async def test_lists_active_and_revoked_shares(api, db, iam, world):
    """Tous les partages du stockage, filtrables par statut."""
    await own_project(db, iam, "p4")
    api.post(URL.format("p1", "st-1"), headers=world.owner, json={"dest_project_id": "p4"})
    api.post(f"/api/v1/shares/{world.share_id}/revoke", headers=world.owner)
    everything = api.get(URL.format("p1", "st-1"), headers=world.owner).json()
    assert everything["total"] == 2
    active = api.get(URL.format("p1", "st-1") + "?status=active", headers=world.owner).json()
    assert [s["dest_project_id"] for s in active["items"]] == ["p4"]


async def test_visible_from_destination_with_view_right(api, world):
    """Depuis p2, un membre avec storage.view voit les partages du stockage partage."""
    response = api.get(URL.format("p2", "st-1"), headers=world.guest)
    assert response.status_code == 200 and response.json()["total"] == 1


async def test_rights_and_visibility(api, iam, world):
    """Sans storage.view, non-membre ou stockage non visible : forbidden."""
    await iam.update_rights(world.guest_id, "p1", [])
    assert api.get(URL.format("p1", "st-1"), headers=world.guest).status_code == 403
    assert api.get(URL.format("p1", "st-1"), headers=world.other).status_code == 403
    assert api.get(URL.format("p1", "st-2"), headers=world.owner).status_code == 403
