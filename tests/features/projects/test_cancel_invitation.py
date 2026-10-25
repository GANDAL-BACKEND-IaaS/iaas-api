"""Cas nominaux et limites de l'annulation d'invitation (F13, R9)."""

from tests.support import login_header


async def test_author_cancels_invitation(client, iam):
    """L'auteur annule une invitation encore envoyee."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    bob = iam.add_user("bob@x.cm", "pw")
    sent = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_id": bob.user_id, "additional_rights": ["vm.view"]},
    ).json()
    response = client.post(f"/api/v1/invitations/{sent['id']}/cancel", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_stranger_cannot_cancel(client, iam):
    """Un tiers ne peut pas annuler l'invitation."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    bob = iam.add_user("bob@x.cm", "pw")
    sent = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_id": bob.user_id, "additional_rights": ["vm.view"]},
    ).json()
    iam.add_user("other@x.cm", "pw")
    other = await login_header(iam, "other@x.cm")
    response = client.post(f"/api/v1/invitations/{sent['id']}/cancel", headers=other)
    assert response.status_code == 403


async def test_removed_inviter_cannot_cancel(client, iam):
    """Un invitant retire du projet ne peut plus annuler son invitation."""
    owner = await login_header(iam)
    project = client.post("/api/v1/projects", headers=owner, json={"name": "Alpha"}).json()
    guest = iam.add_user("guest@x.cm", "pw")
    invitation = client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        headers=owner,
        json={"invitee_id": guest.user_id, "additional_rights": ["project.invite"]},
    ).json()
    guest_headers = await login_header(iam, "guest@x.cm")
    accepted = client.post(
        f"/api/v1/invitations/{invitation['id']}/accept", headers=guest_headers
    )
    assert accepted.status_code == 200
    bob = iam.add_user("bob@x.cm", "pw")
    sent = client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        headers=guest_headers,
        json={"invitee_id": bob.user_id},
    ).json()
    await iam.remove_member(guest.user_id, project["id"])
    response = client.post(f"/api/v1/invitations/{sent['id']}/cancel", headers=guest_headers)
    assert response.status_code == 403


async def test_non_member_cannot_cancel_even_an_accepted_invitation(client, iam):
    """Le membership est verifie avant l'etat de l'invitation (pas de fuite de statut)."""
    owner = await login_header(iam)
    project = client.post("/api/v1/projects", headers=owner, json={"name": "Alpha"}).json()
    guest = iam.add_user("guest@x.cm", "pw")
    invitation = client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        headers=owner,
        json={"invitee_id": guest.user_id},
    ).json()
    guest_headers = await login_header(iam, "guest@x.cm")
    assert client.post(
        f"/api/v1/invitations/{invitation['id']}/accept", headers=guest_headers
    ).status_code == 200
    await iam.remove_member(guest.user_id, project["id"])
    response = client.post(
        f"/api/v1/invitations/{invitation['id']}/cancel", headers=guest_headers
    )
    assert response.status_code == 403


def test_cancel_invitation_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/invitations/inv-1/cancel").status_code == 401
