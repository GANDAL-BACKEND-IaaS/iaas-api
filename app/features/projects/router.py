"""Routes projets, membres et invitations. Proprietaire : ZUCHUON.

Chaque route declare son schema entrant, son schema sortant et ses erreurs.
L'implementation metier reste a completer dans service.py.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.application.ports.dns import DnsPort
from app.application.ports.hypervisor import HypervisorPort
from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort
from app.application.ports.notifications import NotificationsPort
from app.application.ports.storage import StoragePort
from app.core.database import get_db
from app.core.dependencies import (
    get_dns,
    get_hypervisor,
    get_iam,
    get_network,
    get_notifications,
    get_storage,
)
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.projects import service
from app.features.projects.schemas import (
    ConfirmIn,
    InvitationCreateIn,
    InvitationOut,
    MemberOut,
    ProjectCreateIn,
    ProjectOut,
    ProjectUpdateIn,
)

router = APIRouter(prefix="/projects", tags=["projets"])
invitations = APIRouter(prefix="/invitations", tags=["invitations"])

_USER = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.VALIDATION_ERROR,
    ErrorCode.NOT_IMPLEMENTED,
)
_WRITE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT,
    ErrorCode.VALIDATION_ERROR,
    ErrorCode.NOT_IMPLEMENTED,
)
_DELETE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.VALIDATION_ERROR,
    ErrorCode.UPSTREAM_UNAVAILABLE,
    ErrorCode.NOT_IMPLEMENTED,
)


@router.post(
    "",
    response_model=ProjectOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_project",
    summary="Creer un projet",
    responses=error_responses(*_WRITE),
)
async def create_project(
    body: ProjectCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ProjectOut:
    """F12 : cree un projet dont l'appelant devient proprietaire."""
    return await service.create_project(db, iam, identity, body.name)


@router.get(
    "",
    response_model=Page[ProjectOut],
    operation_id="list_projects",
    summary="Lister mes projets",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR, ErrorCode.NOT_IMPLEMENTED),
)
async def list_projects(
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[ProjectOut]:
    """F12 : liste paginee des projets de l'appelant."""
    return await service.list_projects(db, iam, identity, params)


@router.get(
    "/{project_id}",
    response_model=ProjectOut,
    operation_id="get_project",
    summary="Consulter un projet",
    responses=error_responses(*_USER),
)
async def get_project(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ProjectOut:
    """F12 : consulte un projet dont l'appelant est membre."""
    return await service.get_project(db, iam, identity, project_id)


@router.patch(
    "/{project_id}",
    response_model=ProjectOut,
    operation_id="rename_project",
    summary="Renommer un projet",
    responses=error_responses(*_WRITE),
)
async def rename_project(
    project_id: str,
    body: ProjectUpdateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ProjectOut:
    """F12 : renomme un projet. Reserve au proprietaire."""
    return await service.rename_project(db, iam, identity, project_id, body.name)


@router.post(
    "/{project_id}/deletion",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_project",
    summary="Supprimer un projet",
    description="Exige une confirmation explicite. Suppression en cascade (R23).",
    responses=error_responses(*_DELETE),
)
async def delete_project(
    project_id: str,
    body: ConfirmIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    network: NetworkPort = Depends(get_network),
    dns: DnsPort = Depends(get_dns),
    storage: StoragePort = Depends(get_storage),
    db: Session = Depends(get_db),
) -> None:
    """F12 : supprime le projet et ce qu'il contient, apres confirmation."""
    await service.delete_project(
        db, iam, hypervisor, network, dns, storage, identity, project_id, body.confirm
    )


@router.get(
    "/{project_id}/members",
    response_model=Page[MemberOut],
    operation_id="list_project_members",
    summary="Lister les membres",
    responses=error_responses(*_USER),
)
async def list_members(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[MemberOut]:
    """F12 : liste paginee des membres du projet."""
    return await service.list_members(db, iam, identity, project_id, params)


@router.post(
    "/{project_id}/invitations",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_invitation",
    summary="Inviter un utilisateur",
    responses=error_responses(*_WRITE),
)
async def create_invitation(
    project_id: str,
    body: InvitationCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    notifications: NotificationsPort = Depends(get_notifications),
    db: Session = Depends(get_db),
) -> InvitationOut:
    """F13 : invite un utilisateur. Les droits d'un invite sont plafonnes aux siens (R8)."""
    return await service.create_invitation(db, iam, notifications, identity, project_id, body)


@router.get(
    "/{project_id}/invitations",
    response_model=Page[InvitationOut],
    operation_id="list_invitations",
    summary="Lister les invitations",
    responses=error_responses(*_USER),
)
async def list_invitations(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[InvitationOut]:
    """F13 : liste paginee des invitations du projet."""
    return await service.list_invitations(db, iam, identity, project_id, params)


@invitations.post(
    "/{invitation_id}/accept",
    response_model=InvitationOut,
    operation_id="accept_invitation",
    summary="Accepter une invitation",
    responses=error_responses(*_WRITE),
)
async def accept_invitation(
    invitation_id: int,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> InvitationOut:
    """F13 : l'invite accepte et devient membre."""
    return await service.accept_invitation(db, iam, identity, invitation_id)


@invitations.post(
    "/{invitation_id}/refuse",
    response_model=InvitationOut,
    operation_id="refuse_invitation",
    summary="Refuser une invitation",
    responses=error_responses(*_WRITE),
)
def refuse_invitation(
    invitation_id: int,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> InvitationOut:
    """F13 : l'invite refuse l'invitation."""
    return service.refuse_invitation(db, identity, invitation_id)


@invitations.post(
    "/{invitation_id}/cancel",
    response_model=InvitationOut,
    operation_id="cancel_invitation",
    summary="Annuler une invitation",
    responses=error_responses(*_WRITE),
)
def cancel_invitation(
    invitation_id: int,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> InvitationOut:
    """F13 : annule une invitation pas encore acceptee (R9)."""
    return service.cancel_invitation(db, identity, invitation_id)
