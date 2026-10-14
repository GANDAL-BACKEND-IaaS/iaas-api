"""Rejets de decode_token : secret, expiration, forme, claims."""

from datetime import timedelta

import jwt
import pytest

from app.application.ports.iam import GlobalRole, Identity, InvalidToken, TokenExpired
from app.core.tokens import decode_token, encode_token

_SECRET = "secret-with-32-bytes-minimum!!"


def _identity() -> Identity:
    return Identity("u1", "ada@x.cm", "Ada", "Lovelace", GlobalRole.USER)


def test_wrong_secret_is_invalid():
    """Un secret different invalide le jeton."""
    token = encode_token(_identity(), _SECRET, timedelta(hours=1)).access_token
    with pytest.raises(InvalidToken):
        decode_token(token, "other-secret-with-32-bytes-min!!")


def test_expired_token_is_rejected():
    """Un jeton expire est distingue d'un jeton simplement invalide."""
    token = encode_token(_identity(), _SECRET, timedelta(seconds=-1)).access_token
    with pytest.raises(TokenExpired):
        decode_token(token, _SECRET)


def test_garbage_token_is_invalid():
    """Une chaine qui n'est pas un JWT est rejetee."""
    with pytest.raises(InvalidToken):
        decode_token("not.a.jwt", _SECRET)


def test_missing_claims_are_invalid():
    """Un jeton sans les claims attendus est invalide."""
    token = jwt.encode({"sub": "u1"}, _SECRET, algorithm="HS256")
    with pytest.raises(InvalidToken):
        decode_token(token, _SECRET)
