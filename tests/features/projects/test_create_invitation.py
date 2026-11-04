"""Cas nominaux et limites de la creation d'invitation (F13, R8)."""

from tests.support import login_header


async def test_owner_invites_with_extra_right(client, iam):
    """Le proprietaire invite avec un droit a la carte."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    bob = iam.add_user("bob@x.cm", "pw")
    response = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_id": bob.user_id, "additional_rights": ["vm.view"]},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "sent"
    assert response.json()["invitee_id"] == bob.user_id
    assert response.json()["invitee_email"] == "bob@x.cm"
    assert response.json()["additional_rights"] == ["vm.view"]


async def test_owner_invites_by_email(client, iam):
    """Le frontend peut inviter directement avec l'email du destinataire."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    bob = iam.add_user("bob@x.cm", "pw")
    response = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"email": "bob@x.cm", "additional_rights": ["vm.view"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["invitee_id"] == bob.user_id
    assert body["invitee_email"] == "bob@x.cm"


async def test_invitation_email_is_normalized(client, iam):
    """L'email est nettoye et la recherche IAM ignore la casse."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    bob = iam.add_user("bob@x.cm", "pw")
    response = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"email": "  BOB@X.CM  "},
    )
    assert response.status_code == 201
    assert response.json()["invitee_id"] == bob.user_id
    assert response.json()["invitee_email"] == "bob@x.cm"


async def test_unknown_invitation_email_is_not_found(client, iam):
    """Un email absent de l'IAM ne cree pas d'invitation."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    response = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"email": "inconnu@x.cm"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_email_invitation_must_be_unique_and_pending(client, iam):
    """Une seconde invitation en attente pour le meme email est refusee."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    iam.add_user("bob@x.cm", "pw")
    first = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"email": "bob@x.cm"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"email": "BOB@X.CM"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


async def test_invitation_rejects_both_or_no_identifier(client, iam):
    """Exactement un des deux champs invitee_id ou email est requis."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    bob = iam.add_user("bob@x.cm", "pw")
    both = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_id": bob.user_id, "email": "bob@x.cm"},
    )
    assert both.status_code == 422
    neither = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"additional_rights": ["vm.view"]},
    )
    assert neither.status_code == 422


async def test_guest_cannot_grant_more_than_he_has(client, iam):
    """Un invite ne peut pas accorder un droit qu'il n'a pas."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, created["id"], ["project.invite", "vm.view"])
    other = iam.add_user("other@x.cm", "pw")
    guest_headers = await login_header(iam, "guest@x.cm")
    response = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=guest_headers,
        json={"invitee_id": other.user_id, "additional_rights": ["vm.delete"]},
    )
    assert response.status_code == 403


def test_create_invitation_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post(
        "/api/v1/projects/p1/invitations", json={"invitee_id": "usr-bob"}
    )
    assert response.status_code == 401
