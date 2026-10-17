"""Cas nominaux et limites de la consultation d'un projet (F12)."""

from tests.support import login_header


async def test_get_project_for_member(client, iam):
    """Un membre consulte son projet."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    response = client.get(f"/api/v1/projects/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Alpha"


async def test_get_project_hidden_from_outsider(client, iam):
    """Un etranger recoit un refus."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    iam.add_user("out@x.cm", "pw")
    outsider = await login_header(iam, "out@x.cm")
    response = client.get(f"/api/v1/projects/{created['id']}", headers=outsider)
    assert response.status_code == 403


def test_get_project_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.get("/api/v1/projects/p1").status_code == 401
