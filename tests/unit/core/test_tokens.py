from datetime import timedelta

import jwt
import pytest

from app.application.ports.iam import GlobalRole, Identity, InvalidToken, TokenExpired
from app.core.tokens import decode_token, encode_token


@pytest.fixture
def identity():
    return Identity("u1", "ada@x.cm", "Ada", "Lovelace", GlobalRole.USER)


@pytest.fixture
def admin():
    return Identity("a1", "root@x.cm", "Grace", "Hopper", GlobalRole.ADMIN)


def test_roundtrip_keeps_claims(identity, admin):
    for ident in (identity, admin):
        token = encode_token(ident, "secret", timedelta(hours=1)).access_token
        assert decode_token(token, "secret") == ident


def test_wrong_secret_is_invalid(identity):
    token = encode_token(identity, "secret", timedelta(hours=1)).access_token
    with pytest.raises(InvalidToken):
        decode_token(token, "other-secret")


def test_expired_token_is_rejected(identity):
    token = encode_token(identity, "secret", timedelta(seconds=-1)).access_token
    with pytest.raises(TokenExpired):
        decode_token(token, "secret")


def test_garbage_token_is_invalid():
    with pytest.raises(InvalidToken):
        decode_token("not.a.jwt", "secret")


def test_missing_claims_are_invalid():
    token = jwt.encode({"sub": "u1"}, "secret", algorithm="HS256")
    with pytest.raises(InvalidToken):
        decode_token(token, "secret")