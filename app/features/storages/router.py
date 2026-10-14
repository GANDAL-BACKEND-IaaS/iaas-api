"""Routes stockage orientees ressource. Proprietaire : TABA."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.application.ports.iam import Identity
from app.core.database import get_db
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.shares.schemas import ShareOut
from app.features.storages import service
from app.features.storages.schemas import (
    ConfirmIn,
    ShareTargetIn,
    StorageOut,
    StorageRequestCreateIn,
    StorageRequestUpdateIn,
)

router = APIRouter(prefix="/projects/{project_id}/storages", tags=["stockages"])

_COMMON = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.VALIDATION_ERROR,
    ErrorCode.INVALID_STATE,
    ErrorCode.NOT_IMPLEMENTED,
    ErrorCode.UPSTREAM_UNAVAILABLE,
)


@router.post(
    "",
    response_model=StorageOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="request_create_storage",
    summary="Demander la creation d'un stockage",
    responses=error_responses(*_COMMON),
)
def request_create_storage(
    project_id: str,
    body: StorageRequestCreateIn,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> StorageOut:
    """F8 : depose une demande de creation liee au projet."""
    return service.request_create_storage(db, identity, project_id, body)


@router.get(
    "",
    response_model=Page[StorageOut],
    operation_id="list_storages",
    summary="Consulter les stockages",
    responses=error_responses(*_COMMON),
)
def list_storages(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[StorageOut]:
    """F10 : liste les stockages du projet, y compris les stockages partages."""
    return service.list_storages(db, identity, project_id, params)


@router.get(
    "/{storage_id}",
    response_model=StorageOut,
    operation_id="get_storage",
    summary="Consulter un stockage",
    responses=error_responses(*_COMMON),
)
def get_storage(
    project_id: str,
    storage_id: str,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> StorageOut:
    """F10 : consulte un stockage visible dans le projet."""
    return service.get_storage(db, identity, project_id, storage_id)


@router.post(
    "/{storage_id}/update-requests",
    response_model=StorageOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="request_update_storage",
    summary="Demander la modification d'un stockage",
    responses=error_responses(*_COMMON),
)
def request_update_storage(
    project_id: str,
    storage_id: str,
    body: StorageRequestUpdateIn,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> StorageOut:
    """F9 : la modification porte uniquement sur la taille."""
    return service.request_update_storage(db, identity, project_id, storage_id, body)


@router.post(
    "/{storage_id}/deletion",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_storage",
    summary="Supprimer un stockage",
    description="Action directe, meme si le stockage contient des donnees. Confirmation exigee.",
    responses=error_responses(*_COMMON),
)
def delete_storage(
    project_id: str,
    storage_id: str,
    body: ConfirmIn,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> None:
    """F11 : supprime le stockage apres confirmation et revoque ses partages."""
    service.delete_storage(db, identity, project_id, storage_id, body.confirm)


@router.post(
    "/{storage_id}/shares",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="share_storage",
    summary="Partager un stockage",
    responses=error_responses(*_COMMON, ErrorCode.CONFLICT),
)
def share_storage(
    project_id: str,
    storage_id: str,
    body: ShareTargetIn,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> ShareOut:
    """F14 : partage le stockage avec un autre projet du meme proprietaire."""
    return service.share_storage(db, identity, project_id, storage_id, body.dest_project_id)
