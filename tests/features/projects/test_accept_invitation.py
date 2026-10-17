"""Cas nominaux et limites de l'acceptation d'invitation (F13)."""

from tests.support import login_header


async def test_invitee_accepts(client, iam):
    """L'invite accepte et devient membre."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    iam.add_user("bob@x.cm", "pw", "Bob", "X")
    sent = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_email": "bob@x.cm", "extra_rights": ["vm.view"]},
    ).json()
    bob = await login_header(iam, "bob@x.cm")
    response = client.post(f"/api/v1/invitations/{sent['id']}/accept", headers=bob)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    members = client.get(f"/api/v1/projects/{created['id']}/members", headers=headers).json()
    assert members["total"] == 2


async def test_stranger_cannot_accept(client, iam):
    """Une autre personne ne peut pas accepter l'invitation."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    sent = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_email": "bob@x.cm", "extra_rights": ["vm.view"]},
    ).json()
    iam.add_user("other@x.cm", "pw")
    other = await login_header(iam, "other@x.cm")
    response = client.post(f"/api/v1/invitations/{sent['id']}/accept", headers=other)
    assert response.status_code == 403


def test_accept_invitation_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/invitations/1/accept").status_code == 401
