"""Routes VM orientees ressource.

Les creations et modifications passent par le moteur de demandes. La console est
conservee dans le contrat ; son implementation technologique viendra plus tard.
"""

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.application.ports.dns import DnsPort
from app.application.ports.hypervisor import HypervisorPort
from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort
from app.core.database import get_db
from app.core.dependencies import get_dns, get_hypervisor, get_iam, get_network
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.requests.schemas import RequestOut, VMCreateRequestIn, VMUpdateRequestIn
from app.features.vms import service
from app.features.vms.schemas import ConsoleOut, PowerOut, VMOut, VMPowerIn
from app.shared.deletion import DeletionIn, DeletionResponse
from app.shared.enums import VmState

router = APIRouter(prefix="/projects/{project_id}/vms", tags=["vms"])

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
    operation_id="request_create_vm",
    summary="Demander la creation d'une VM",
    responses=error_responses(*_COMMON),
)
async def request_create_vm(
    project_id: str,
    body: VMCreateRequestIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """F1 : depose une demande de creation. La VM n'existe qu'apres acceptation."""
    return await service.request_create_vm(db, iam, identity, project_id, body)


@router.get(
    "",
    response_model=Page[VMOut],
    operation_id="list_vms",
    summary="Voir l'etat des VMs",
    responses=error_responses(*_COMMON),
)
async def list_vms(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    state: VmState | None = Query(default=None),
    shared: bool | None = Query(default=None),
    ip_address: str | None = Query(default=None, max_length=45),
    name: str | None = Query(default=None, max_length=128),
) -> Page[VMOut]:
    """F3 : liste les VMs du projet, y compris les VMs partagees."""
    return await service.list_vms(
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
    "/{vm_id}",
    response_model=VMOut,
    operation_id="get_vm",
    summary="Consulter une VM",
    responses=error_responses(*_COMMON),
)
async def get_vm(
    project_id: str,
    vm_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> VMOut:
    """F3 : consulte une VM visible dans le projet."""
    return await service.get_vm(db, iam, identity, project_id, vm_id)


@router.post(
    "/{vm_id}/update-requests",
    response_model=RequestOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="request_update_vm",
    summary="Demander la modification d'une VM",
    responses=error_responses(*_COMMON, ErrorCode.CONFLICT),
)
async def request_update_vm(
    project_id: str,
    vm_id: str,
    body: VMUpdateRequestIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """F2 : depose une demande de modification de la configuration complete."""
    return await service.request_update_vm(db, iam, identity, project_id, vm_id, body)


@router.post(
    "/{vm_id}/power",
    response_model=PowerOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="power_vm",
    summary="Demarrer, arreter ou redemarrer une VM",
    responses=error_responses(*_COMMON),
)
async def power_vm(
    project_id: str,
    vm_id: str,
    body: VMPowerIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    db: Session = Depends(get_db),
) -> PowerOut:
    """F4 : action directe, sans demande ni administrateur."""
    return await service.power_vm(
        db, iam, hypervisor, identity, project_id, vm_id, body.action
    )


@router.post(
    "/{vm_id}/console",
    response_model=ConsoleOut,
    operation_id="console_vm",
    summary="Acceder a la console d'une VM",
    responses=error_responses(*_COMMON),
)
async def console_vm(
    project_id: str,
    vm_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    db: Session = Depends(get_db),
) -> ConsoleOut:
    """F5 : verifie le droit et le partage actif a chaque acces."""
    return await service.console_vm(db, iam, hypervisor, identity, project_id, vm_id)


@router.post(
    "/{vm_id}/deletion",
    response_model=DeletionResponse,
    operation_id="delete_vm",
    summary="Supprimer une VM",
    description="Protocole en deux temps : apercu sans confirmation_text, puis texte exact.",
    responses=error_responses(*_COMMON, ErrorCode.BAD_REQUEST),
)
async def delete_vm(
    project_id: str,
    vm_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    network: NetworkPort = Depends(get_network),
    dns: DnsPort = Depends(get_dns),
    db: Session = Depends(get_db),
    body: DeletionIn = Body(default_factory=DeletionIn),
):
    """F6 : apercu puis suppression effective de la VM."""
    return await service.delete_vm(
        db,
        iam,
        hypervisor,
        network,
        dns,
        identity,
        project_id,
        vm_id,
        body.confirmation_text,
    )
