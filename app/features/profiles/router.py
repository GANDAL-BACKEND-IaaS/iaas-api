"""Routes du catalogue de droits et des profils.

La consultation est ouverte a tout utilisateur connecte. La mutation est reservee a l'administrateur.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError, ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity, require_admin
from app.features.profiles import service
from app.features.profiles.schemas import ProfileCreateIn, ProfileOut, ProfileUpdateIn, RightOut

router = APIRouter(prefix="/admin")

_READ = (ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR)
_WRITE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT,
    ErrorCode.VALIDATION_ERROR,
)


def _translate(exc: service.ProfileError) -> AppError:
    """Traduit une erreur de profil en erreur API stable."""
    if isinstance(exc, service.ProfileNotFound):
        return AppError(ErrorCode.NOT_FOUND, "Profil introuvable.")
    if isinstance(exc, service.ProfileNameTaken):
        return AppError(ErrorCode.CONFLICT, "Ce nom de profil existe deja.")
    return AppError(ErrorCode.VALIDATION_ERROR, f"Droits inconnus : {exc}.")


@router.get(
    "/rights",
    response_model=list[RightOut],
    tags=["profils & droits (consultation)"],
    operation_id="list_rights",
    summary="Lister le catalogue de droits",
    responses=error_responses(*_READ),
    dependencies=[Depends(get_current_identity)],
)
def list_rights(db: Session = Depends(get_db)) -> list[RightOut]:
    """Tableau complet des droits assignables, trie par code."""
    return [RightOut.model_validate(right) for right in service.list_rights(db)]


@router.get(
    "/profiles",
    response_model=Page[ProfileOut],
    tags=["profils & droits (consultation)"],
    operation_id="list_profiles",
    summary="Lister les profils de droits",
    responses=error_responses(*_READ),
    dependencies=[Depends(get_current_identity)],
)
def list_profiles(
    db: Session = Depends(get_db), params: PageParams = Depends(get_page_params)
) -> Page[ProfileOut]:
    """Liste paginee des profils, triee par nom."""
    items = service.list_profiles(db)
    start = (params.page - 1) * params.page_size
    chunk = items[start:start + params.page_size]
    return Page.build([ProfileOut.model_validate(item) for item in chunk], len(items), params)


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
def create_profile(body: ProfileCreateIn, db: Session = Depends(get_db)) -> ProfileOut:
    """Cree un profil de droits. Reserve a un administrateur."""
    try:
        return ProfileOut.model_validate(
            service.create_profile(db, body.name, body.description, body.rights)
        )
    except service.ProfileError as exc:
        raise _translate(exc) from None


@router.patch(
    "/profiles/{profile_id}",
    response_model=ProfileOut,
    tags=["admin: gestion des profils"],
    operation_id="update_profile",
    summary="Modifier un profil",
    responses=error_responses(*_WRITE),
    dependencies=[Depends(require_admin)],
)
def update_profile(
    profile_id: str, body: ProfileUpdateIn, db: Session = Depends(get_db)
) -> ProfileOut:
    """Modifie le nom, la description ou les droits d'un profil."""
    try:
        return ProfileOut.model_validate(
            service.update_profile(db, profile_id, body.name, body.description, body.rights)
        )
    except service.ProfileError as exc:
        raise _translate(exc) from None


@router.delete(
    "/profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["admin: gestion des profils"],
    operation_id="delete_profile",
    summary="Supprimer un profil",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND),
    dependencies=[Depends(require_admin)],
)
def delete_profile(profile_id: str, db: Session = Depends(get_db)) -> Response:
    """Supprime un profil. Les invitations et membres conservent leurs droits additionnels."""
    try:
        service.delete_profile(db, profile_id)
    except service.ProfileError as exc:
        raise _translate(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
