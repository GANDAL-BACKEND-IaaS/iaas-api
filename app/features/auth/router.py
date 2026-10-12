from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.application.ports.iam import (
    EmailAlreadyUsed,
    IamPort,
    Identity,
    InvalidCredentials,
    UserNotFound,
    UserUpdate,
)
from app.core.database import get_db
from app.core.dependencies import get_iam, get_token_decoder
from app.features.auth import service
from app.features.auth.dependencies import get_current_identity
from app.features.auth.schemas import (
    IdentityOut,
    LoginIn,
    PasswordChangeIn,
    TokenOut,
    UserUpdateIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, iam: IamPort = Depends(get_iam),
                decode: Callable[[str], Identity] = Depends(get_token_decoder),
                db: Session = Depends(get_db)):
    try:
        token = await iam.login(body.email, body.password)
        identity = decode(token.access_token)
    except InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect") from None
    service.ensure_reference(db, identity)
    return TokenOut.of(token)


@router.get("/me", response_model=IdentityOut)
async def me(identity: Identity = Depends(get_current_identity)):
    return IdentityOut.of(identity)


@router.patch("/me", response_model=TokenOut)
async def update_me(body: UserUpdateIn, identity: Identity = Depends(get_current_identity),
                    iam: IamPort = Depends(get_iam)):
    """Renvoie un nouveau jeton reflétant les informations modifiées."""
    try:
        token = await iam.update_user(identity.user_id, UserUpdate(**body.model_dump()))
    except EmailAlreadyUsed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette adresse email est déjà utilisée") from None
    except UserNotFound:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable") from None
    return TokenOut.of(token)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChangeIn, identity: Identity = Depends(get_current_identity),
                          iam: IamPort = Depends(get_iam)):
    try:
        await iam.change_password(identity.user_id, body.old_password, body.new_password)
    except InvalidCredentials:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ancien mot de passe incorrect") from None
    except UserNotFound:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(identity: Identity = Depends(get_current_identity),
                    iam: IamPort = Depends(get_iam), db: Session = Depends(get_db)):
    try:
        await iam.delete_account(identity.user_id)
    except UserNotFound:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable") from None
    service.remove_reference(db, identity.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)