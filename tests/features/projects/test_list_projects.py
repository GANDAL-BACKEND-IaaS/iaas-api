"""Cas nominaux et limites de la liste des projets (F12)."""

from tests.support import login_header


async def test_list_projects_returns_owned(client, iam):
    """L'appelant ne voit que ses projets."""
    headers = await login_header(iam)
    client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"})
    response = client.get("/api/v1/projects", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "Alpha"


def test_list_projects_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects").status_code == 401
