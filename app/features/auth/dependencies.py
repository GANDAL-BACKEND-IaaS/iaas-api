from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.ports.iam import GlobalRole, Identity, InvalidToken, TokenExpired
from app.core.dependencies import get_token_decoder

_bearer = HTTPBearer(auto_error=False)
_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


async def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    decode: Callable[[str], Identity] = Depends(get_token_decoder),
) -> Identity:
    """Bloque la requête si le jeton est absent, invalide ou expiré (vérifié localement)."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton manquant", headers=_UNAUTHORIZED)
    try:
        return decode(credentials.credentials)
    except TokenExpired:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton expiré", headers=_UNAUTHORIZED) from None
    except InvalidToken:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide", headers=_UNAUTHORIZED) from None


async def require_admin(identity: Identity = Depends(get_current_identity)) -> Identity:
    if identity.role != GlobalRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé aux administrateurs")
    return identity