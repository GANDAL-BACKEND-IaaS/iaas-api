"""Cas nominaux et limites de delete_storage (F11, R6, R19)."""

import asyncio

from sqlalchemy import select

from app.features.storages import service
from app.shared.enums import StorageState
from app.shared.models.audit import AuditLog
from app.shared.models.shares import ResourceShare
from app.shared.models.storages import Storage

URL = "/api/v1/projects/{}/storages/{}/deletion"


def _delete(api, headers, project_id="p1", storage_id="st-1", confirm=True):
    body = {"confirm": True} if confirm else {}
    return api.post(URL.format(project_id, storage_id), headers=headers, json=body)


async def test_without_confirmation_returns_the_warning(api, db, storage_port, world):
    """Sans confirm : bad_request avec l'avertissement, rien n'est touche."""
    for body in ({}, {"confirm": False}):
        response = api.post(URL.format("p1", "st-1"), headers=world.owner, json=body)
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "bad_request" and error["details"] == {"confirm_required": True}
        assert "definitive" in error["message"] and "1 partage(s)" in error["message"]
    assert "st-1" in storage_port.spaces
    assert db.get(Storage, "st-1").state == StorageState.AVAILABLE.value


async def test_confirmed_deletion_revokes_shares(api, db, storage_port, world):
    """Avec confirm : appel au port, partages revoques, stockage invisible partout, audit."""
    assert _delete(api, world.owner).status_code == 204
    assert "st-1" not in storage_port.spaces
    assert db.get(Storage, "st-1") is None
    assert db.get(ResourceShare, world.share_id).status == "revoked"
    listing = api.get("/api/v1/projects/p2/storages", headers=world.guest).json()
    assert [item["name"] for item in listing["items"]] == ["media"]
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "storage.deleted"))
    assert entry.actor_id == world.owner_id
    assert entry.data["revoked_shares"] == [world.share_id]
    assert _delete(api, world.owner).status_code == 404


async def test_guest_needs_storage_delete(api, iam, world):
    """storage.delete est un droit a la carte ; dans p2, ce sont les droits de p2 qui comptent."""
    assert _delete(api, world.guest).status_code == 403
    await iam.update_rights(world.guest_id, "p2", ["storage.view", "storage.delete"])
    assert _delete(api, world.guest, project_id="p2").status_code == 204


async def test_storage_group_down_applies_nothing(api, db, storage_port, world):
    """Groupe Stockage indisponible : 503, etat et partages inchanges."""
    storage_port.available = False
    response = _delete(api, world.owner)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_unavailable"
    assert db.get(Storage, "st-1").state == StorageState.AVAILABLE.value
    assert db.get(ResourceShare, world.share_id).status == "active"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "storage.deleted")) is None


async def test_timeout_is_reported_as_unavailable(api, db, storage_port, world, monkeypatch):
    """Un appel qui depasse le delai maximal est traite comme une indisponibilite."""

    async def slow(_ref):
        await asyncio.sleep(1)

    monkeypatch.setattr(storage_port, "delete_storage", slow)
    monkeypatch.setattr(service, "STORAGE_CALL_TIMEOUT_SECONDS", 0.01)
    assert _delete(api, world.owner).status_code == 503
    assert db.get(Storage, "st-1").state == StorageState.AVAILABLE.value


async def test_interrupted_deletion_can_be_resumed(api, db, world):
    """Un stockage reste en deleting apres une interruption se supprime a nouveau."""
    db.get(Storage, "st-1").state = StorageState.DELETING.value
    db.commit()
    assert _delete(api, world.owner).status_code == 204
    assert db.get(Storage, "st-1") is None


async def test_not_visible_and_missing_token(api, world):
    """Stockage d'un autre projet : forbidden. Sans jeton : unauthorized."""
    assert _delete(api, world.owner, storage_id="st-3").status_code == 403
    response = api.post(URL.format("p1", "st-1"), json={"confirm": True})
    assert response.status_code == 401
