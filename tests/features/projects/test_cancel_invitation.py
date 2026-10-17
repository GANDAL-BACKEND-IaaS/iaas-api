"""Cas nominaux et limites de l'annulation d'invitation (F13, R9)."""

from tests.support import login_header


async def test_author_cancels_invitation(client, iam):
    """L'auteur annule une invitation encore envoyee."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    sent = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_email": "bob@x.cm", "extra_rights": ["vm.view"]},
    ).json()
    response = client.post(f"/api/v1/invitations/{sent['id']}/cancel", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_stranger_cannot_cancel(client, iam):
    """Un tiers ne peut pas annuler l'invitation."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    sent = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_email": "bob@x.cm", "extra_rights": ["vm.view"]},
    ).json()
    iam.add_user("other@x.cm", "pw")
    other = await login_header(iam, "other@x.cm")
    response = client.post(f"/api/v1/invitations/{sent['id']}/cancel", headers=other)
    assert response.status_code == 403


def test_cancel_invitation_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/invitations/1/cancel").status_code == 401
