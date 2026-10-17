"""Cas nominaux et limites de la liste des membres (F12)."""

from tests.support import login_header


async def test_list_members_includes_owner(client, iam):
    """Le proprietaire apparait dans les membres."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    response = client.get(f"/api/v1/projects/{created['id']}/members", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["role"] == "owner"


def test_list_members_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1/members").status_code == 401
