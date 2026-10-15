"""Cas nominaux et limites de get_storage (F10)."""

from app.shared.enums import ShareStatus
from app.shared.models.shares import ResourceShare

URL = "/api/v1/projects/{}/storages/{}"


async def test_view_from_origin_and_from_destination(api, world):
    """Le meme stockage, vu de son origine puis du projet destinataire du partage."""
    origin = api.get(URL.format("p1", "st-1"), headers=world.owner).json()
    assert (origin["name"], origin["size"], origin["shared"], origin["state"]) == (
        "backup", 50, False, "available")
    shared = api.get(URL.format("p2", "st-1"), headers=world.guest)
    assert shared.status_code == 200 and shared.json()["shared"] is True


async def test_not_visible_or_unknown(api, db, world):
    """Stockage non visible dans le projet : forbidden. Stockage inconnu : not_found."""
    assert api.get(URL.format("p1", "st-2"), headers=world.owner).status_code == 403
    assert api.get(URL.format("p1", "absent"), headers=world.owner).status_code == 404
    db.get(ResourceShare, world.share_id).status = ShareStatus.REVOKED.value
    db.commit()
    assert api.get(URL.format("p2", "st-1"), headers=world.guest).status_code == 403


async def test_requires_membership_and_token(api, world):
    """Non-membre : forbidden. Sans jeton : unauthorized."""
    assert api.get(URL.format("p1", "st-1"), headers=world.other).status_code == 403
    response = api.get(URL.format("p1", "st-1"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
