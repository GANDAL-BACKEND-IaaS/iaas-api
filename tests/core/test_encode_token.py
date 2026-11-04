"""Aller-retour d'un jeton : encode_token conserve les claims."""

from datetime import timedelta

from app.application.ports.iam import GlobalRole, Identity
from app.core.tokens import decode_token, encode_token


def test_encode_token_roundtrip_keeps_claims():
    """Le jeton emis contient l'identite et le role, pour un utilisateur et un admin."""
    identities = (
        Identity("u1", "ada@x.cm", "Ada", "Lovelace", GlobalRole.USER),
        Identity("a1", "root@x.cm", "Grace", "Hopper", GlobalRole.ADMIN),
    )
    for identity in identities:
        token = encode_token(identity, "secret-with-32-bytes-minimum!!", timedelta(hours=1))
        assert decode_token(token.access_token, "secret-with-32-bytes-minimum!!") == identity
        assert token.expires_in == 3600
        assert token.token_type == "bearer"
