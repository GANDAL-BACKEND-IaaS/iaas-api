"""Routes du catalogue de droits et des profils. Proprietaire : ZUCHUON.

La consultation est ouverte a tout utilisateur connecte. La mutation est reservee a l'administrateur.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity, require_admin
from app.features.profiles import service
from app.features.profiles.schemas import ProfileCreate, ProfileOut, ProfileUpdate, RightOut

router = APIRouter(prefix="/admin")

_READ = (ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR)
_WRITE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT,
    ErrorCode.VALIDATION_ERROR,
)


def _http(exc: service.ProfileError):
    """Traduit une erreur de profil en erreur API stable."""
    if isinstance(exc, service.ProfileNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Profil introuvable")
    if isinstance(exc, service.ProfileNameTaken):
        return HTTPException(status.HTTP_409_CONFLICT, "Ce nom de profil existe deja")
    return HTTPException(422, f"Droits inconnus : {exc}")


def _page(items: list, params: PageParams, model):
    """Decoupe une liste deja chargee en page. Les catalogues restent petits."""
    start = (params.page - 1) * params.page_size
    chunk = items[start:start + params.page_size]
    return Page(items=[model.model_validate(item) for item in chunk], total=len(items), page=params.page, page_size=params.page_size)


@router.get(
    "/rights",
    response_model=Page[RightOut],
    tags=["profils & droits (consultation)"],
    operation_id="list_rights",
    summary="Lister le catalogue de droits",
    responses=error_responses(*_READ),
    dependencies=[Depends(get_current_identity)],
)
def list_rights(db: Session = Depends(get_db), params: PageParams = Depends(get_page_params)) -> Page[RightOut]:
    """Liste paginee des droits assignables."""
    return _page(service.list_rights(db), params, RightOut)


@router.get(
    "/profiles",
    response_model=Page[ProfileOut],
    tags=["profils & droits (consultation)"],
    operation_id="list_profiles",
    summary="Lister les profils de droits",
    responses=error_responses(*_READ),
    dependencies=[Depends(get_current_identity)],
)
def list_profiles(db: Session = Depends(get_db), params: PageParams = Depends(get_page_params)) -> Page[ProfileOut]:
    """Liste paginee des profils, y compris ceux definis par l'administrateur."""
    return _page(service.list_profiles(db), params, ProfileOut)


@router.post(
    "/profiles",
    response_model=ProfileOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: gestion des profils"],
    operation_id="create_profile",
    summary="Creer un profil",
    responses=error_responses(*_WRITE),
    dependencies=[Depends(require_admin)],
)
def create_profile(body: ProfileCreate, db: Session = Depends(get_db)) -> ProfileOut:
    """Cree un profil de droits. Reserve a un administrateur."""
    try:
        return service.create_profile(db, body.name, body.description, body.rights)
    except service.ProfileError as exc:
        raise _http(exc) from None


@router.patch(
    "/profiles/{profile_id}",
    response_model=ProfileOut,
    tags=["admin: gestion des profils"],
    operation_id="update_profile",
    summary="Modifier un profil",
    responses=error_responses(*_WRITE),
    dependencies=[Depends(require_admin)],
)
def update_profile(profile_id: int, body: ProfileUpdate, db: Session = Depends(get_db)) -> ProfileOut:
    """Modifie le nom, la description ou les droits d'un profil."""
    try:
        return service.update_profile(db, profile_id, body.name, body.description, body.rights)
    except service.ProfileError as exc:
        raise _http(exc) from None


@router.delete(
    "/profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["admin: gestion des profils"],
    operation_id="delete_profile",
    summary="Supprimer un profil",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND),
    dependencies=[Depends(require_admin)],
)
def delete_profile(profile_id: int, db: Session = Depends(get_db)) -> Response:
    """Supprime un profil. Les invitations conservent leur instantane de droits."""
    try:
        service.delete_profile(db, profile_id)
    except service.ProfileError as exc:
        raise _http(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
