"""Cas nominaux et limites de la creation d'invitation (F13, R8)."""

from tests.support import login_header


async def test_owner_invites_with_extra_right(client, iam):
    """Le proprietaire invite avec un droit a la carte."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    response = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_email": "bob@x.cm", "extra_rights": ["vm.view"]},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "sent"
    assert response.json()["rights_snapshot"] == ["vm.view"]


async def test_guest_cannot_grant_more_than_he_has(client, iam):
    """Un invite ne peut pas accorder un droit qu'il n'a pas."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    guest = iam.add_user("guest@x.cm", "pw")
    await iam.invite_user(guest.user_id, created["id"], ["project.invite", "vm.view"])
    guest_headers = await login_header(iam, "guest@x.cm")
    response = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=guest_headers,
        json={"invitee_email": "other@x.cm", "extra_rights": ["vm.delete"]},
    )
    assert response.status_code == 403


def test_create_invitation_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    response = client.post(
        "/api/v1/projects/p1/invitations", json={"invitee_email": "a@b.cm"}
    )
    assert response.status_code == 401
