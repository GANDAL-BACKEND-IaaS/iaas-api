"""Route reservee get_vm : elle repond 501 tant que le proprietaire ne l'implemente pas."""

from tests.support import login_header


async def test_get_vm_is_not_implemented(client, iam):
    """Le contrat est publie, l'implementation metier reste a ecrire."""
    headers = await login_header(iam, "u@x.cm")
    response = client.request("GET", "/api/v1/projects/p1/vms/vm-1", headers=headers)
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "not_implemented"
    assert body["error"]["message"]


async def test_get_vm_requires_a_token(client):
    """Sans jeton, la route refuse avant meme d'atteindre l'implementation."""
    response = client.request("GET", "/api/v1/projects/p1/vms/vm-1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
