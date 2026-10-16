"""Tests de la route GET /projects/{project_id}/networks (list_networks)."""

from tests.support import login_header, own_project


async def test_list_networks_requires_a_token(client):
    """Sans jeton, la route refuse avec 401 unauthorized."""
    response = client.request("GET", "/api/v1/projects/p1/networks")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_list_networks_empty(client, db, iam):
    """Projet sans reseau : page vide."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    response = client.request("GET", "/api/v1/projects/p1/networks", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 20


async def test_list_networks_paginated(client, db, iam):
    """Pagination conforme (items, total, page, page_size)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")

    for i in range(3):
        client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": f"lan-{i}"})

    r1 = client.request("GET", "/api/v1/projects/p1/networks?page=1&page_size=2", headers=headers)
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["total"] == 3
    assert len(b1["items"]) == 2
    assert b1["page"] == 1

    r2 = client.request("GET", "/api/v1/projects/p1/networks?page=2&page_size=2", headers=headers)
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["total"] == 3
    assert len(b2["items"]) == 1
    assert b2["page"] == 2


async def test_list_networks_by_guest_with_vm_view(client, db, iam):
    """Un invite avec vm.view peut consulter la liste des reseaux."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    owner_headers = await login_header(iam, "u@x.cm")
    client.request("POST", "/api/v1/projects/p1/networks", headers=owner_headers, json={"name": "lan-view"})

    iam.add_user("viewer@x.cm", "pw", "View", "Er")
    uid = await iam.login("viewer@x.cm", "pw")
    viewer_identity = await iam.validate_token(uid.access_token)
    await iam.invite_user(viewer_identity.user_id, "p1", ["vm.view"])

    viewer_headers = await login_header(iam, "viewer@x.cm")
    response = client.request("GET", "/api/v1/projects/p1/networks", headers=viewer_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "lan-view"


async def test_list_networks_by_non_member_fails(client, db, iam):
    """Un non-membre ne peut pas lister les reseaux (403)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    iam.add_user("stranger@x.cm", "pw", "St", "Ranger")

    headers = await login_header(iam, "stranger@x.cm")
    response = client.request("GET", "/api/v1/projects/p1/networks", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_list_networks_works_when_upstream_is_down(client, db, iam, fake_network):
    """La consultation reste possible quand le service externe est en panne (etat en base)."""
    await own_project(db, iam, project_id="p1", email="u@x.cm")
    headers = await login_header(iam, "u@x.cm")
    client.request("POST", "/api/v1/projects/p1/networks", headers=headers, json={"name": "lan-resilient"})

    fake_network.available = False
    response = client.request("GET", "/api/v1/projects/p1/networks", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "lan-resilient"
