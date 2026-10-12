from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.features.auth.dependencies import get_current_identity, require_admin
from app.features.profiles import service
from app.features.profiles.schemas import ProfileCreate, ProfileOut, ProfileUpdate, RightOut

router = APIRouter(prefix="/admin")


def _http(exc: service.ProfileError) -> HTTPException:
    if isinstance(exc, service.ProfileNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Profil introuvable")
    if isinstance(exc, service.ProfileNameTaken):
        return HTTPException(status.HTTP_409_CONFLICT, "Ce nom de profil existe déjà")
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Droits inconnus : {exc}")


@router.get("/rights", response_model=list[RightOut], tags=["profils & droits (consultation)"],
            dependencies=[Depends(get_current_identity)])
def list_rights(db: Session = Depends(get_db)):
    return service.list_rights(db)


@router.get("/profiles", response_model=list[ProfileOut], tags=["profils & droits (consultation)"],
            dependencies=[Depends(get_current_identity)])
def list_profiles(db: Session = Depends(get_db)):
    return service.list_profiles(db)


@router.post("/profiles", response_model=ProfileOut, status_code=status.HTTP_201_CREATED,
             tags=["admin: gestion des profils"], dependencies=[Depends(require_admin)])
def create_profile(body: ProfileCreate, db: Session = Depends(get_db)):
    try:
        return service.create_profile(db, body.name, body.description, body.rights)
    except service.ProfileError as exc:
        raise _http(exc) from None


@router.patch("/profiles/{profile_id}", response_model=ProfileOut,
              tags=["admin: gestion des profils"], dependencies=[Depends(require_admin)])
def update_profile(profile_id: int, body: ProfileUpdate, db: Session = Depends(get_db)):
    try:
        return service.update_profile(db, profile_id, body.name, body.description, body.rights)
    except service.ProfileError as exc:
        raise _http(exc) from None


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT,
               tags=["admin: gestion des profils"], dependencies=[Depends(require_admin)])
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    try:
        service.delete_profile(db, profile_id)
    except service.ProfileError as exc:
        raise _http(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)