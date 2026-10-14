"""Route reservee create_network : elle repond 501 tant que le proprietaire ne l'implemente pas."""

from tests.support import login_header


async def test_create_network_is_not_implemented(client, iam):
    """Le contrat est publie, l'implementation metier reste a ecrire."""
    headers = await login_header(iam, "u@x.cm")
    response = client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={'name': 'lan'})
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "not_implemented"
    assert body["error"]["message"]


async def test_create_network_requires_a_token(client):
    """Sans jeton, la route refuse avant meme d'atteindre l'implementation."""
    response = client.request("POST", "/api/v1/projects/p1/networks", json={'name': 'lan'})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
