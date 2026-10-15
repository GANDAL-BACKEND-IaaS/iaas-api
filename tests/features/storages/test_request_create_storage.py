"""Cas nominaux et limites de request_create_storage (F8, R1, R2)."""

import pytest
from sqlalchemy import select

from app.shared.models.audit import AuditLog
from app.shared.models.storages import Storage

URL = "/api/v1/projects/{}/storages"


def _create(api, headers, project_id="p1", **body):
    return api.post(URL.format(project_id), headers=headers,
                    json={"name": "archives", "size": 200} | body)


async def test_owner_creates_a_pending_request(api, db, world):
    """Le proprietaire depose une demande en attente, sans creer de stockage."""
    response = _create(api, world.owner, name="  archives  ")
    assert response.status_code == 201
    body = response.json()
    assert (body["kind"], body["status"], body["project_id"]) == ("storage_create", "pending", "p1")
    assert body["payload"] == {"name": "archives", "size": 200}
    assert body["author_id"] == world.owner_id
    assert db.scalar(select(Storage).where(Storage.name == "archives")) is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "request.submitted"))


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "   "}, {"size": 0}, {"size": -3},
                                  {"name": "x" * 129}])
async def test_invalid_body_is_rejected(api, world, body):
    """Nom vide ou trop long, taille nulle ou negative : validation_error."""
    response = _create(api, world.owner, **body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_guest_without_right_is_forbidden(api, iam, world):
    """storage.request_create est un droit a la carte, absent des profils."""
    response = _create(api, world.guest)
    assert response.status_code == 403
    assert "storage.request_create" in response.json()["error"]["message"]
    await iam.update_rights(world.guest_id, "p1", ["storage.view", "storage.request_create"])
    assert _create(api, world.guest).status_code == 201


async def test_non_member_unknown_project_and_missing_token(api, world):
    """Non-membre : forbidden. Projet inconnu : not_found. Sans jeton : unauthorized."""
    assert _create(api, world.other).status_code == 403
    assert _create(api, world.owner, project_id="inconnu").status_code == 404
    assert api.post(URL.format("p1"), json={"name": "a", "size": 1}).status_code == 401
