"""Routes reseau. Proprietaire : KOM. Action directe, sans demande (F7, R21)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort
from app.core.database import get_db
from app.core.dependencies import get_iam, get_network
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.networks import service
from app.features.networks.schemas import NetworkCreateIn, NetworkMembershipIn, NetworkOut

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
    responses=error_responses(*_COMMON),
)
async def create_network(
    project_id: str,
    body: NetworkCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    port: NetworkPort = Depends(get_network),
    db: Session = Depends(get_db),
) -> NetworkOut:
    """F7 : cree un reseau dans le projet."""
    return await service.create_network(db, iam, port, identity, project_id, body.name)


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
    return await service.list_networks(db, iam, identity, project_id, params)


@router.post(
    "/{network_id}/vms",
    response_model=NetworkOut,
    operation_id="attach_vm_to_network",
    summary="Rattacher une VM",
    responses=error_responses(*_COMMON, ErrorCode.CONFLICT),
)
async def attach_vm(
    project_id: str,
    network_id: str,
    body: NetworkMembershipIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    port: NetworkPort = Depends(get_network),
    db: Session = Depends(get_db),
) -> NetworkOut:
    """F7 : rattache une VM visible dans le projet, partagee ou non (R21)."""
    return await service.attach_vm(db, iam, port, identity, project_id, network_id, body.vm_id)


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
    port: NetworkPort = Depends(get_network),
    db: Session = Depends(get_db),
) -> NetworkOut:
    """F7 : retire une VM du reseau."""
    return await service.detach_vm(db, iam, port, identity, project_id, network_id, vm_id)


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
    port: NetworkPort = Depends(get_network),
    db: Session = Depends(get_db),
) -> None:
    """F7 : supprime le reseau."""
    await service.delete_network(db, iam, port, identity, project_id, network_id)
