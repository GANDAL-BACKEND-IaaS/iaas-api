"""Cas nominaux et limites de la creation de projet (F12)."""

from tests.support import login_header


async def test_create_project_makes_caller_owner(client, iam):
    """L'appelant devient proprietaire du projet cree."""
    headers = await login_header(iam)
    response = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alpha"
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert body["owner_id"] == me["user_id"]


async def test_created_ids_are_uuid_strings(client, iam):
    """Tous les identifiants crees par l'API sont des UUID sous forme de chaine."""
    import uuid

    headers = await login_header(iam)
    project = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    request = client.post(
        f"/api/v1/projects/{project['id']}/vms",
        headers=headers,
        json={"name": "web", "configuration": {"ram_gb": 1, "vcpu": 1, "vram_gb": 0, "ssd_gb": 10}},
    ).json()
    bob = iam.add_user("bob@x.cm", "pw")
    invitation = client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        headers=headers,
        json={"invitee_id": bob.user_id},
    ).json()
    for value in (project["id"], request["id"], invitation["id"]):
        assert isinstance(value, str)
        assert str(uuid.UUID(value)) == value


async def test_admin_cannot_create_project(client, iam):
    """Un administrateur traite les demandes, il ne cree pas de projet."""
    headers = await login_header(iam, "root@x.cm")
    response = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"})
    assert response.status_code == 403


def test_create_project_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/projects", json={"name": "Alpha"}).status_code == 401
