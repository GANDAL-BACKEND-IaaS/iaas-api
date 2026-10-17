"""Cas nominaux et limites du renommage de projet (F12)."""

from tests.support import login_header


async def test_owner_renames_project(client, iam):
    """Le proprietaire renomme son projet."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    response = client.patch(
        f"/api/v1/projects/{created['id']}", headers=headers, json={"name": "Beta"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Beta"


async def test_guest_cannot_rename(client, iam):
    """Un invite ne renomme pas le projet."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, created["id"], ["vm.view"])
    guest_headers = await login_header(iam, "guest@x.cm")
    response = client.patch(
        f"/api/v1/projects/{created['id']}", headers=guest_headers, json={"name": "Pirate"}
    )
    assert response.status_code == 403


def test_rename_project_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.patch("/api/v1/projects/p1", json={"name": "Beta"}).status_code == 401
