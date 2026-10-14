"""Route reservee create_pack : elle repond 501 tant que le proprietaire ne l'implemente pas."""

from tests.support import login_header


async def test_create_pack_is_not_implemented(client, iam):
    """Le contrat est publie, l'implementation metier reste a ecrire."""
    headers = await login_header(iam, "root@x.cm")
    response = client.request("POST", "/api/v1/admin/packs", headers=headers, json={'name': 'Mini', 'ram': 1, 'cpu': 1, 'vram': 1, 'ssd': 1})
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "not_implemented"
    assert body["error"]["message"]


async def test_create_pack_requires_a_token(client):
    """Sans jeton, la route refuse avant meme d'atteindre l'implementation."""
    response = client.request("POST", "/api/v1/admin/packs", json={'name': 'Mini', 'ram': 1, 'cpu': 1, 'vram': 1, 'ssd': 1})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
