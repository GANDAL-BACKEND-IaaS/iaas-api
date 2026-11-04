"""Routes d'identite. Proprietaire : ZUCHUON.

Le backend ne gere pas les comptes : il delegue au port IAM et ne conserve qu'une reference.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.application.ports.hypervisor import HypervisorPort
from app.application.ports.iam import (
    EmailAlreadyUsed,
    IamPort,
    Identity,
    InvalidCredentials,
    UserNotFound,
    UserUpdate,
)
from app.application.ports.network import NetworkPort
from app.core.database import get_db
from app.core.dependencies import (
    get_hypervisor,
    get_iam,
    get_network,
    get_token_decoder,
)
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth import service
from app.features.auth.dependencies import get_current_identity, require_admin
from app.features.auth.schemas import (
    IdentityOut,
    LoginIn,
    PasswordChangeIn,
    RegisterIn,
    TokenOut,
    UserUpdateIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin", tags=["admin: gestion des comptes"])

_AUTH = (ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR)
_ADMIN = (ErrorCode.UNAUTHORIZED, ErrorCode.FORBIDDEN, ErrorCode.VALIDATION_ERROR)


@admin_router.get(
    "/users",
    response_model=Page[IdentityOut],
    operation_id="list_users",
    summary="Lister les utilisateurs",
    description="Retourne les identites de tous les comptes connus de l'IAM, administrateurs inclus.",
    responses=error_responses(*_ADMIN),
)
async def list_users(
    iam: IamPort = Depends(get_iam),
    _: Identity = Depends(require_admin),
    params: PageParams = Depends(get_page_params),
) -> Page[IdentityOut]:
    """Liste les identites IAM avec la pagination standard de l'API."""
    identities, total = await iam.list_users(
        offset=(params.page - 1) * params.page_size,
        limit=params.page_size,
    )
    return Page.build([IdentityOut.of(identity) for identity in identities], total, params)


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="register",
    summary="Créer un compte",
    responses=error_responses(ErrorCode.CONFLICT, ErrorCode.VALIDATION_ERROR),
)
async def register(
    body: RegisterIn,
    iam: IamPort = Depends(get_iam),
    decode: Callable[[str], Identity] = Depends(get_token_decoder),
    db: Session = Depends(get_db),
) -> TokenOut:
    """Cree un compte IAM, conserve sa reference et renvoie le jeton emis."""
    try:
        token = await iam.register_user(
            body.email, body.password, body.first_name, body.last_name
        )
    except EmailAlreadyUsed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette adresse email est deja utilisee") from None
    service.ensure_reference(db, decode(token.access_token))
    return TokenOut.of(token)


@admin_router.post(
    "/admins",
    response_model=IdentityOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_admin",
    summary="Créer un administrateur",
    responses=error_responses(
        ErrorCode.UNAUTHORIZED,
        ErrorCode.FORBIDDEN,
        ErrorCode.CONFLICT,
        ErrorCode.VALIDATION_ERROR,
    ),
)
async def create_admin(
    body: RegisterIn,
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    _: Identity = Depends(require_admin),
) -> IdentityOut:
    """Cree un compte admin dans l'IAM et conserve sa reference locale."""
    try:
        identity = await iam.create_admin(
            body.email, body.password, body.first_name, body.last_name
        )
    except EmailAlreadyUsed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette adresse email est deja utilisee") from None
    service.ensure_reference(db, identity)
    return IdentityOut.of(identity)


@router.post(
    "/login",
    response_model=TokenOut,
    operation_id="login",
    summary="Se connecter",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR),
)
async def login(
    body: LoginIn,
    iam: IamPort = Depends(get_iam),
    decode: Callable[[str], Identity] = Depends(get_token_decoder),
    db: Session = Depends(get_db),
) -> TokenOut:
    """Echange un email et un mot de passe contre un jeton Bearer."""
    try:
        token = await iam.login(body.email, body.password)
        identity = decode(token.access_token)
    except InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect") from None
    service.ensure_reference(db, identity)
    return TokenOut.of(token)


@router.get(
    "/me",
    response_model=IdentityOut,
    operation_id="get_me",
    summary="Lire son identite",
    responses=error_responses(*_AUTH),
)
async def me(identity: Identity = Depends(get_current_identity)) -> IdentityOut:
    """Retourne l'identite portee par le jeton courant."""
    return IdentityOut.of(identity)


@router.patch(
    "/me",
    response_model=TokenOut,
    operation_id="update_me",
    summary="Modifier son identite",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.CONFLICT, ErrorCode.VALIDATION_ERROR),
)
async def update_me(
    body: UserUpdateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
) -> TokenOut:
    """Met a jour les informations et renvoie un nouveau jeton."""
    try:
        token = await iam.update_user(identity.user_id, UserUpdate(**body.model_dump()))
    except EmailAlreadyUsed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette adresse email est deja utilisee") from None
    except UserNotFound:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable") from None
    return TokenOut.of(token)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="change_password",
    summary="Changer son mot de passe",
    responses=error_responses(ErrorCode.BAD_REQUEST, ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR),
)
async def change_password(
    body: PasswordChangeIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
) -> Response:
    """Remplace le mot de passe apres verification de l'ancien."""
    try:
        await iam.change_password(identity.user_id, body.old_password, body.new_password)
    except InvalidCredentials:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ancien mot de passe incorrect") from None
    except UserNotFound:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_me",
    summary="Supprimer son compte",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.UPSTREAM_UNAVAILABLE),
)
async def delete_me(
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    network: NetworkPort = Depends(get_network),
    db: Session = Depends(get_db),
) -> Response:
    """Supprime le compte et ses projets, puis nettoie ses contributions."""
    try:
        await service.delete_account_cascade(
            db, iam, hypervisor, network, identity
        )
    except UserNotFound:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Compte introuvable") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
