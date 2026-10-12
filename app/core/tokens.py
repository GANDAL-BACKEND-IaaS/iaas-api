from datetime import UTC, datetime, timedelta

import jwt

from app.application.ports.iam import AuthToken, GlobalRole, Identity, InvalidToken, TokenExpired

_ALGORITHM = "HS256"


def _claims_to_identity(claims: dict) -> Identity:
    return Identity(
        user_id=claims["sub"],
        email=claims["email"],
        first_name=claims["first_name"],
        last_name=claims["last_name"],
        role=GlobalRole(claims["role"]),
    )


def encode_token(identity: Identity, secret: str, ttl: timedelta) -> AuthToken:
    """Émet un jeton auto-porteur (utilisé côté IAM)."""
    now = datetime.now(UTC)
    claims = {
        "sub": identity.user_id,
        "email": identity.email,
        "first_name": identity.first_name,
        "last_name": identity.last_name,
        "role": identity.role.value,
        "iat": now,
        "exp": now + ttl,
    }
    token = jwt.encode(claims, secret, algorithm=_ALGORITHM)
    return AuthToken(access_token=token, expires_in=int(ttl.total_seconds()))


def decode_token(token: str, secret: str) -> Identity:
    """Valide localement un jeton émis par l'IAM (signature + expiration + claims)."""
    try:
        claims = jwt.decode(
            token, secret, algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )
        return _claims_to_identity(claims)
    except jwt.ExpiredSignatureError:
        raise TokenExpired() from None
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise InvalidToken() from None