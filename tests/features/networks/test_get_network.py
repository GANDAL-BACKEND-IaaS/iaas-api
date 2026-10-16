"""Tests de la route GET /projects/{project_id}/networks/{network_id} (get_network)."""

from tests.support import login_header, own_project


async def test_get_network_requires_a_token(client):
    """Sans jeton -> 401 unauthorized."""
    response = client.request("GET", "/api/v1/projects/p1/networks/net-1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_get_network_nominal(client, db, iam):
    """Consulter un reseau existant renvoie 200 et son etat."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-main"}
    )
    net_id = create_res.json()["id"]

    response = client.request("GET", f"/api/v1/projects/p1/networks/{net_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == net_id
    assert body["name"] == "lan-main"
    assert body["project_id"] == "p1"
    assert body["vm_ids"] == []


async def test_get_network_nonexistent(client, db, iam):
    """Reseau introuvable -> 404 not_found."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    response = client.request("GET", "/api/v1/projects/p1/networks/unknown-net", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_get_network_from_another_project_fails(client, db, iam):
    """Un reseau appartenant a p1 ne peut pas etre consulte via l'URL de p2 (404, pas de fuite)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    await own_project(db, iam, project_id="p2", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-p1"}
    )
    net_id = create_res.json()["id"]

    # Tentative d'acces a net_id sous /projects/p2/networks/net_id
    response = client.request("GET", f"/api/v1/projects/p2/networks/{net_id}", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_get_network_works_when_upstream_is_down(client, db, iam, fake_network):
    """La consultation unitaire fonctionne meme si le port Reseau est indisponible."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    create_res = client.request(
        "POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-robust"}
    )
    net_id = create_res.json()["id"]

    fake_network.available = False
    response = client.request("GET", f"/api/v1/projects/p1/networks/{net_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "lan-robust"
