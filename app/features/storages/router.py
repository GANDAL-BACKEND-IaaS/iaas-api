"""Routes stockage orientees ressource."""

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.storage import StoragePort
from app.core.database import get_db
from app.core.dependencies import get_iam
from app.core.dependencies import get_storage as get_storage_port
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.requests.schemas import (
    RequestOut,
    StorageCreateRequestIn,
    StorageUpdateRequestIn,
)
from app.features.storages import service
from app.features.storages.schemas import StorageOut
from app.shared.deletion import DeletionIn, DeletionResponse
from app.shared.enums import StorageState

router = APIRouter(prefix="/projects/{project_id}/storages", tags=["stockages"])

_COMMON = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.VALIDATION_ERROR,
    ErrorCode.INVALID_STATE,
    ErrorCode.UPSTREAM_UNAVAILABLE,
)


@router.post(
    "",
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="request_create_storage",
    summary="Demander la creation d'un stockage",
    responses=error_responses(*_COMMON),
)
async def request_create_storage(
    project_id: str,
    body: StorageCreateRequestIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """F8 : depose une demande de creation liee au projet."""
    return await service.request_create_storage(db, iam, identity, project_id, body)


@router.get(
    "",
    response_model=Page[StorageOut],
    operation_id="list_storages",
    summary="Consulter les stockages",
    responses=error_responses(*_COMMON),
)
async def list_storages(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    state: StorageState | None = Query(default=None),
    shared: bool | None = Query(default=None),
    ip_address: str | None = Query(default=None, max_length=45),
    name: str | None = Query(default=None, max_length=128),
) -> Page[StorageOut]:
    """F10 : liste les stockages du projet, y compris les stockages partages."""
    return await service.list_storages(
        db,
        iam,
        identity,
        project_id,
        params,
        state=state,
        shared=shared,
        ip_address=ip_address,
        name=name,
    )


@router.get(
    "/{storage_id}",
    response_model=StorageOut,
    operation_id="get_storage",
    summary="Consulter un stockage",
    responses=error_responses(*_COMMON),
)
async def get_storage(
    project_id: str,
    storage_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> StorageOut:
    """F10 : consulte un stockage visible dans le projet."""
    return await service.get_storage(db, iam, identity, project_id, storage_id)


@router.post(
    "/{storage_id}/update-requests",
    response_model=RequestOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="request_update_storage",
    summary="Demander la modification d'un stockage",
    responses=error_responses(*_COMMON, ErrorCode.BAD_REQUEST, ErrorCode.CONFLICT),
)
async def request_update_storage(
    project_id: str,
    storage_id: str,
    body: StorageUpdateRequestIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """F9 : la modification porte uniquement sur la taille."""
    return await service.request_update_storage(
        db, iam, identity, project_id, storage_id, body
    )


@router.post(
    "/{storage_id}/deletion",
    response_model=DeletionResponse,
    operation_id="delete_storage",
    summary="Supprimer un stockage",
    description="Protocole en deux temps. Les donnees sont perdues meme si le stockage est non vide.",
    responses=error_responses(*_COMMON, ErrorCode.BAD_REQUEST),
)
async def delete_storage(
    project_id: str,
    storage_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    port: StoragePort = Depends(get_storage_port),
    db: Session = Depends(get_db),
    body: DeletionIn = Body(default_factory=DeletionIn),
):
    """F11 : apercu puis suppression effective du stockage."""
    return await service.delete_storage(
        db, iam, port, identity, project_id, storage_id, body.confirmation_text
    )
