"""Routes reseau. Proprietaire : KOM. Action directe, sans demande (F7, R21)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort
from app.core.database import get_db
from app.core.dependencies import get_iam
from app.core.dependencies import get_network as get_network_port
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.networks import service
from app.features.networks.schemas import (
    NetworkCreateIn,
    NetworkMembershipIn,
    NetworkOut,
    NetworkUpdateIn,
)

router = APIRouter(prefix="/projects/{project_id}/networks", tags=["reseaux"])

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
    response_model=NetworkOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_network",
    summary="Creer un reseau",
    responses=error_responses(*_COMMON, ErrorCode.CONFLICT),
)
async def create_network(
    project_id: str,
    body: NetworkCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    network: NetworkPort = Depends(get_network_port),
    db: Session = Depends(get_db),
) -> NetworkOut:
    """F7 : cree un reseau dans le projet."""
    row = await service.create_network(
        db,
        iam,
        network,
        actor_id=identity.user_id,
        project_id=project_id,
        name=body.name,
    )
    return NetworkOut.model_validate(row)


@router.get(
    "",
    response_model=Page[NetworkOut],
    operation_id="list_networks",
    summary="Lister les reseaux",
    responses=error_responses(*_COMMON),
)
async def list_networks(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[NetworkOut]:
    """F7 : liste paginee des reseaux du projet."""
    rows, total = await service.list_networks(
        db,
        iam,
        actor_id=identity.user_id,
        project_id=project_id,
        params=params,
    )
    return Page[NetworkOut](
        items=[NetworkOut.model_validate(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/{network_id}",
    response_model=NetworkOut,
    operation_id="get_network",
    summary="Consulter un reseau",
    responses=error_responses(*_COMMON),
)
async def get_network(
    project_id: str,
    network_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> NetworkOut:
    """Consulte un reseau au sein d'un projet."""
    row = await service.get_network(
        db,
        iam,
        actor_id=identity.user_id,
        project_id=project_id,
        network_id=network_id,
    )
    return NetworkOut.model_validate(row)


@router.patch(
    "/{network_id}",
    response_model=NetworkOut,
    operation_id="update_network",
    summary="Renommer un reseau",
    responses=error_responses(*_COMMON, ErrorCode.CONFLICT),
)
async def update_network(
    project_id: str,
    network_id: str,
    body: NetworkUpdateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> NetworkOut:
    """Renomme un reseau au sein d'un projet."""
    row = await service.rename_network(
        db,
        iam,
        actor_id=identity.user_id,
        project_id=project_id,
        network_id=network_id,
        new_name=body.name,
    )
    return NetworkOut.model_validate(row)


@router.post(
    "/{network_id}/vms",
    response_model=NetworkOut,
    operation_id="attach_vm_to_network",
    summary="Rattacher une VM",
    responses=error_responses(*_COMMON, ErrorCode.CONFLICT, ErrorCode.BAD_REQUEST),
)
async def attach_vm(
    project_id: str,
    network_id: str,
    body: NetworkMembershipIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    network: NetworkPort = Depends(get_network_port),
    db: Session = Depends(get_db),
) -> NetworkOut:
    """F7 : rattache une VM visible dans le projet, partagee ou non (R21)."""
    row = await service.attach_vm(
        db,
        iam,
        network,
        actor_id=identity.user_id,
        project_id=project_id,
        network_id=network_id,
        vm_id=body.vm_id,
    )
    return NetworkOut.model_validate(row)


@router.delete(
    "/{network_id}/vms/{vm_id}",
    response_model=NetworkOut,
    operation_id="detach_vm_from_network",
    summary="Retirer une VM du reseau",
    responses=error_responses(*_COMMON),
)
async def detach_vm(
    project_id: str,
    network_id: str,
    vm_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    network: NetworkPort = Depends(get_network_port),
    db: Session = Depends(get_db),
) -> NetworkOut:
    """F7 : retire une VM du reseau."""
    row = await service.detach_vm(
        db,
        iam,
        network,
        actor_id=identity.user_id,
        project_id=project_id,
        network_id=network_id,
        vm_id=vm_id,
    )
    return NetworkOut.model_validate(row)


@router.delete(
    "/{network_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_network",
    summary="Supprimer un reseau",
    responses=error_responses(*_COMMON),
)
async def delete_network(
    project_id: str,
    network_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    network: NetworkPort = Depends(get_network_port),
    db: Session = Depends(get_db),
) -> None:
    """F7 : supprime le reseau."""
    await service.delete_network(
        db,
        iam,
        network,
        actor_id=identity.user_id,
        project_id=project_id,
        network_id=network_id,
    )
