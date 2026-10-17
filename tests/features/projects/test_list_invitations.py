"""Cas nominaux et limites de la liste des invitations (F13)."""

from tests.support import login_header


async def test_list_invitations(client, iam):
    """Le proprietaire liste les invitations du projet."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_email": "bob@x.cm", "extra_rights": ["vm.view"]},
    )
    response = client.get(f"/api/v1/projects/{created['id']}/invitations", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_list_invitations_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1/invitations").status_code == 401
