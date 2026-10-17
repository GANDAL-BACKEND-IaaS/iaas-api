"""Cas nominaux et limites du refus d'invitation (F13)."""

from tests.support import login_header


async def test_invitee_refuses(client, iam):
    """L'invite refuse l'invitation."""
    headers = await login_header(iam)
    created = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha"}).json()
    iam.add_user("bob@x.cm", "pw")
    sent = client.post(
        f"/api/v1/projects/{created['id']}/invitations",
        headers=headers,
        json={"invitee_email": "bob@x.cm", "extra_rights": ["vm.view"]},
    ).json()
    bob = await login_header(iam, "bob@x.cm")
    response = client.post(f"/api/v1/invitations/{sent['id']}/refuse", headers=bob)
    assert response.status_code == 200
    assert response.json()["status"] == "refused"


def test_refuse_invitation_requires_a_token(client):
    """Sans jeton, la route est refusee."""
    assert client.post("/api/v1/invitations/1/refuse").status_code == 401
