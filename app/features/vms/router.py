"""Routes VM orientees ressource. Proprietaire : NAOMI.

Le moteur partage POST /api/v1/requests traite deja le depot et la decision.
Ces routes exposent le contrat que NAOMI implementera.
"""

from fastapi import APIRouter, Depends, status
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
from app.features.requests.schemas import RequestOut
from app.features.shares.schemas import ShareOut
from app.features.vms import service
from app.features.vms.schemas import (
    ConfirmIn,
    ConsoleOut,
    PowerIn,
    ShareTargetIn,
    VmOut,
    VmRequestCreateIn,
    VmRequestUpdateIn,
)

router = APIRouter(prefix="/projects/{project_id}/vms", tags=["vms"])

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
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="request_create_vm",
    summary="Demander la creation d'une VM",
    responses=error_responses(*_COMMON),
)
async def request_create_vm(
    project_id: str,
    body: VmRequestCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """F1 : depose une demande de creation. La VM n'existe qu'apres acceptation."""
    return await service.request_create_vm(db, iam, identity, project_id, body)


@router.get(
    "",
    response_model=Page[VmOut],
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
) -> Page[VmOut]:
    """F3 : liste les VMs du projet, y compris les VMs partagees."""
    return await service.list_vms(db, iam, identity, project_id, params)


@router.get(
    "/{vm_id}",
    response_model=VmOut,
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
) -> VmOut:
    """F3 : consulte une VM visible dans le projet."""
    return await service.get_vm(db, iam, identity, project_id, vm_id)


@router.post(
    "/{vm_id}/update-requests",
    response_model=RequestOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="request_update_vm",
    summary="Demander la modification d'une VM",
    responses=error_responses(*_COMMON),
)
async def request_update_vm(
    project_id: str,
    vm_id: str,
    body: VmRequestUpdateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """F2 : depose une demande de modification des caracteristiques de base."""
    return await service.request_update_vm(db, iam, identity, project_id, vm_id, body)


@router.post(
    "/{vm_id}/power",
    response_model=VmOut,
    operation_id="power_vm",
    summary="Demarrer, arreter ou redemarrer une VM",
    responses=error_responses(*_COMMON),
)
async def power_vm(
    project_id: str,
    vm_id: str,
    body: PowerIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    db: Session = Depends(get_db),
) -> VmOut:
    """F4 : action directe, sans demande ni administrateur."""
    return await service.power_vm(db, iam, hypervisor, identity, project_id, vm_id, body.action)


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
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_vm",
    summary="Supprimer une VM",
    description="Action directe. Exige une confirmation. Revoque les partages et demande la suppression DNS.",
    responses=error_responses(*_COMMON),
)
async def delete_vm(
    project_id: str,
    vm_id: str,
    body: ConfirmIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    network: NetworkPort = Depends(get_network),
    dns: DnsPort = Depends(get_dns),
    db: Session = Depends(get_db),
) -> None:
    """F6 : supprime la VM apres confirmation explicite."""
    await service.delete_vm(
        db, iam, hypervisor, network, dns, identity, project_id, vm_id, body.confirm
    )


@router.post(
    "/{vm_id}/shares",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="share_vm",
    summary="Partager une VM",
    responses=error_responses(*_COMMON, ErrorCode.CONFLICT),
)
async def share_vm(
    project_id: str,
    vm_id: str,
    body: ShareTargetIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ShareOut:
    """F14 : partage la VM avec un autre projet du meme proprietaire."""
    return await service.share_vm(db, iam, identity, project_id, vm_id, body.dest_project_id)
