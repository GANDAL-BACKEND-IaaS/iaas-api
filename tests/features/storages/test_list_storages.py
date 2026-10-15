"""Cas nominaux et limites de list_storages (F10)."""

from sqlalchemy import select

from app.shared.enums import ShareStatus
from app.shared.models.shares import ResourceShare
from tests.support import add_storage

URL = "/api/v1/projects/{}/storages"


async def test_shared_storages_are_listed_and_flagged(api, world):
    """Dans p2 : son stockage, plus celui partage depuis p1 avec shared=true."""
    body = api.get(URL.format("p2"), headers=world.guest).json()
    assert {(i["name"], i["shared"], i["origin_project_id"]) for i in body["items"]} == {
        ("backup", True, "p1"),
        ("media", False, "p2"),
    }
    assert (body["total"], body["page"], body["page_size"]) == (2, 1, 20)
    origin = api.get(URL.format("p1"), headers=world.owner).json()
    assert [(i["name"], i["shared"]) for i in origin["items"]] == [("backup", False)]


async def test_pagination(api, db, world):
    """Pages disjointes et total exact."""
    for index in range(4):
        add_storage(db, "p1", f"extra-{index}", name=f"extra-{index}", size=1)
    pages = [
        api.get(URL.format("p1") + f"?page={page}&page_size=2", headers=world.owner).json()
        for page in (1, 2, 3)
    ]
    names = [item["name"] for page in pages for item in page["items"]]
    assert pages[0]["total"] == 5 and len(names) == 5 == len(set(names))
    too_big = api.get(URL.format("p1") + "?page_size=500", headers=world.owner)
    assert too_big.status_code == 422


async def test_revoked_share_hides_the_storage(api, db, world):
    """Un partage revoque ne rend plus le stockage visible."""
    db.get(ResourceShare, world.share_id).status = ShareStatus.REVOKED.value
    db.commit()
    body = api.get(URL.format("p2"), headers=world.guest).json()
    assert [i["name"] for i in body["items"]] == ["media"]
    assert db.scalar(select(ResourceShare.status)) == "revoked"


async def test_rights_and_membership(api, iam, world):
    """Sans storage.view : forbidden. Non-membre : forbidden. Projet inconnu : not_found."""
    await iam.update_rights(world.guest_id, "p2", [])
    assert api.get(URL.format("p2"), headers=world.guest).status_code == 403
    assert api.get(URL.format("p1"), headers=world.other).status_code == 403
    assert api.get(URL.format("inconnu"), headers=world.owner).status_code == 404


async def test_listing_works_while_storage_group_is_down(api, storage_port, world):
    """La consultation lit la base : elle reste possible si le groupe Stockage est en panne."""
    storage_port.available = False
    assert api.get(URL.format("p1"), headers=world.owner).status_code == 200
