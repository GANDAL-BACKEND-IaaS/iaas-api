"""Routes projets, membres et invitations.

Les suppressions suivent le protocole commun en deux temps (section 1.5).
"""

from fastapi import APIRouter, Body, Depends, Query, Response, status
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
    InvitationCreateIn,
    InvitationOut,
    MemberRightsUpdateIn,
    ProjectCreateIn,
    ProjectMemberOut,
    ProjectOut,
    ProjectUpdateIn,
)
from app.shared.deletion import DeletionIn, DeletionResponse
from app.shared.enums import InvitationStatus, MembershipRole

router = APIRouter(prefix="/projects", tags=["projets"])
invitations = APIRouter(prefix="/invitations", tags=["invitations"])

_USER = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.VALIDATION_ERROR,
)
_MEMBER_DELETE = (*_USER, ErrorCode.UPSTREAM_UNAVAILABLE)
_WRITE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT,
    ErrorCode.VALIDATION_ERROR,
)
_DELETE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.BAD_REQUEST,
    ErrorCode.UPSTREAM_UNAVAILABLE,
    ErrorCode.VALIDATION_ERROR,
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
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR),
)
async def list_projects(
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[ProjectOut]:
    """F12 : liste paginee des projets de l'appelant, triee par nom."""
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
    response_model=DeletionResponse,
    operation_id="delete_project",
    summary="Supprimer un projet",
    description="Protocole en deux temps. Suppression en cascade des ressources du projet (R23).",
    responses=error_responses(*_DELETE),
)
async def delete_project(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    network: NetworkPort = Depends(get_network),
    dns: DnsPort = Depends(get_dns),
    storage: StoragePort = Depends(get_storage),
    db: Session = Depends(get_db),
    body: DeletionIn = Body(default_factory=DeletionIn),
):
    """F12 : apercu puis suppression effective du projet et de ses ressources."""
    return await service.delete_project(
        db,
        iam,
        hypervisor,
        network,
        dns,
        storage,
        identity,
        project_id,
        body.confirmation_text,
    )


@router.get(
    "/{project_id}/members",
    response_model=Page[ProjectMemberOut],
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
    role: MembershipRole | None = Query(default=None),
) -> Page[ProjectMemberOut]:
    """F12 : liste paginee des membres du projet, filtrable par role."""
    return await service.list_members(
        db, iam, identity, project_id, params, role=role
    )


@router.put(
    "/{project_id}/members/{user_id}/rights",
    response_model=ProjectMemberOut,
    operation_id="update_member_rights",
    summary="Modifier les droits d'un membre",
    responses=error_responses(*_WRITE),
)
async def update_member_rights(
    project_id: str,
    user_id: str,
    body: MemberRightsUpdateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ProjectMemberOut:
    """F12 : remplace le profil et/ou les droits additionnels d'un invite."""
    return await service.update_member_rights(
        db, iam, identity, project_id, user_id, body
    )


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="remove_project_member",
    summary="Retirer un membre",
    responses=error_responses(*_MEMBER_DELETE),
)
async def remove_member(
    project_id: str,
    user_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    network: NetworkPort = Depends(get_network),
    db: Session = Depends(get_db),
) -> Response:
    """F12 : retire un invite du projet. Le proprietaire ne peut pas etre retire."""
    await service.remove_member(db, iam, network, identity, project_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    return await service.create_invitation(
        db, iam, notifications, identity, project_id, body
    )


@router.get(
    "/{project_id}/invitations",
    response_model=Page[InvitationOut],
    operation_id="list_invitations",
    summary="Lister les invitations d'un projet",
    responses=error_responses(*_USER),
)
async def list_invitations(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    invitation_status: InvitationStatus | None = Query(default=None, alias="status"),
    invitee_id: str | None = Query(default=None),
) -> Page[InvitationOut]:
    """F13 : liste paginee des invitations du projet."""
    return await service.list_project_invitations(
        db,
        iam,
        identity,
        project_id,
        params,
        status=invitation_status,
        invitee_id=invitee_id,
    )


@invitations.get(
    "",
    response_model=Page[InvitationOut],
    operation_id="list_my_invitations",
    summary="Lister mes invitations",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR),
)
def list_my_invitations(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    invitation_status: InvitationStatus | None = Query(default=None, alias="status"),
) -> Page[InvitationOut]:
    """F13 : invitations recues par l'appelant."""
    return service.list_my_invitations(
        db, identity, params, status=invitation_status
    )


@invitations.post(
    "/{invitation_id}/accept",
    response_model=InvitationOut,
    operation_id="accept_invitation",
    summary="Accepter une invitation",
    responses=error_responses(*_WRITE),
)
async def accept_invitation(
    invitation_id: str,
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
    invitation_id: str,
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
async def cancel_invitation(
    invitation_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> InvitationOut:
    """F13 : annule une invitation pas encore acceptee (R9)."""
    return await service.cancel_invitation(db, iam, identity, invitation_id)
