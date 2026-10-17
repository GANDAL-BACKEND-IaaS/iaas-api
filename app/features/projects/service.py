"""Projets, membres et invitations. Proprietaire : ZUCHUON (port IAM).

La table projects et le port IAM partagent le meme identifiant de projet.
La propriete ne se transfere pas.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.dns import DnsPort
from app.application.ports.hypervisor import HypervisorPort
from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort, NetworkRef, NetworkUnavailable
from app.application.ports.notifications import Notification, NotificationsPort
from app.application.ports.storage import StoragePort
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import Page, PageParams, paginate
from app.features.profiles.service import ProfileError, resolve_rights
from app.features.projects.schemas import InvitationCreateIn, InvitationOut, MemberOut, ProjectOut
from app.features.shares.service import revoke_received_by_project
from app.features.storages.service import delete_storage
from app.features.vms.service import delete_vm
from app.shared.enums import InvitationStatus, MembershipRole
from app.shared.models.networks import Network
from app.shared.models.projects import Invitation, Membership, Project
from app.shared.models.storages import Storage
from app.shared.models.vms import Vm


def _project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


async def _must_be_member(iam: IamPort, user_id: str, project_id: str) -> None:
    if project_id not in await iam.list_projects(user_id):
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur n'est pas membre du projet.")


def _out_invitation(row: Invitation) -> InvitationOut:
    return InvitationOut.model_validate(row)


async def create_project(db: Session, iam: IamPort, identity: Identity, name: str) -> Project:
    """F12 : cree un projet dont l'appelant devient proprietaire."""
    project_id = str(uuid.uuid4())
    await iam.create_project(identity.user_id, project_id)
    project = Project(id=project_id, name=name, owner_id=identity.user_id)
    db.add(project)
    db.add(
        Membership(
            project_id=project_id,
            user_id=identity.user_id,
            role=MembershipRole.OWNER.value,
        )
    )
    record_audit(
        db,
        actor_id=identity.user_id,
        action="project.created",
        entity_type="project",
        entity_id=project_id,
    )
    db.commit()
    db.refresh(project)
    return project


async def list_projects(
    db: Session, iam: IamPort, identity: Identity, params: PageParams
) -> Page[ProjectOut]:
    """F12 : liste paginee des projets de l'appelant."""
    ids = await iam.list_projects(identity.user_id)
    if not ids:
        return Page[ProjectOut](items=[], total=0, page=params.page, page_size=params.page_size)
    statement = select(Project).where(Project.id.in_(ids)).order_by(Project.created_at.desc())
    rows, total = paginate(db, statement, params)
    return Page[ProjectOut](
        items=[ProjectOut.model_validate(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def get_project(db: Session, iam: IamPort, identity: Identity, project_id: str) -> Project:
    """F12 : consulte un projet dont l'appelant est membre."""
    await _must_be_member(iam, identity.user_id, project_id)
    return _project(db, project_id)


async def rename_project(
    db: Session, iam: IamPort, identity: Identity, project_id: str, name: str
) -> Project:
    """F12 : renomme un projet. Reserve au proprietaire."""
    project = _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    if project.owner_id != identity.user_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul le proprietaire peut renommer le projet.")
    project.name = name
    record_audit(
        db,
        actor_id=identity.user_id,
        action="project.renamed",
        entity_type="project",
        entity_id=project_id,
        data={"name": name},
    )
    db.commit()
    db.refresh(project)
    return project


async def delete_project(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    network: NetworkPort,
    dns: DnsPort,
    storage: StoragePort,
    identity: Identity,
    project_id: str,
    confirm: bool,
) -> None:
    """F12 : supprime le projet et ce qu'il contient, apres confirmation (R23)."""
    if confirm is not True:
        raise AppError(ErrorCode.VALIDATION_ERROR, "La suppression exige une confirmation explicite.")
    project = _project(db, project_id)
    if project.owner_id != identity.user_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul le proprietaire peut supprimer le projet.")
    vm_ids = list(db.scalars(select(Vm.id).where(Vm.origin_project_id == project_id)))
    for vm_id in vm_ids:
        await delete_vm(
            db, iam, hypervisor, network, dns, identity, project_id, vm_id, True
        )
    storage_ids = list(
        db.scalars(select(Storage.id).where(Storage.origin_project_id == project_id))
    )
    for storage_id in storage_ids:
        await delete_storage(db, iam, storage, identity, project_id, storage_id, True)
    await revoke_received_by_project(
        db, network, actor_id=identity.user_id, project_id=project_id
    )
    for row in db.scalars(select(Network).where(Network.project_id == project_id)):
        try:
            await network.delete_network(NetworkRef(row.id))
        except NetworkUnavailable:
            db.rollback()
            raise upstream_unavailable("Reseau") from None
        db.delete(row)
    record_audit(
        db,
        actor_id=identity.user_id,
        action="project.deleted",
        entity_type="project",
        entity_id=project_id,
    )
    db.delete(project)
    db.commit()
    await iam.delete_project(project_id)


async def list_members(
    db: Session, iam: IamPort, identity: Identity, project_id: str, params: PageParams
) -> Page[MemberOut]:
    """F12 : liste paginee des membres du projet."""
    _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    grants = await iam.list_members(project_id)
    items = [
        MemberOut(
            user_id=grant.user_id,
            role=MembershipRole.OWNER if grant.is_owner else MembershipRole.GUEST,
            rights=sorted(grant.rights),
        )
        for grant in grants
    ]
    start = (params.page - 1) * params.page_size
    return Page[MemberOut](
        items=items[start:start + params.page_size],
        total=len(items),
        page=params.page,
        page_size=params.page_size,
    )


async def create_invitation(
    db: Session,
    iam: IamPort,
    notifications: NotificationsPort,
    identity: Identity,
    project_id: str,
    body: InvitationCreateIn,
) -> Invitation:
    """F13 : invite un utilisateur. Les droits d'un invite sont plafonnes aux siens."""
    project = _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    rights = await iam.get_rights(identity.user_id, project_id)
    if "project.invite" not in rights:
        raise AppError(ErrorCode.FORBIDDEN, "Droit requis manquant : project.invite.")
    try:
        granted = resolve_rights(db, body.profile_id, body.extra_rights)
    except ProfileError as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Droits invalides : {exc}") from None
    if project.owner_id != identity.user_id and not granted <= rights:
        raise AppError(ErrorCode.FORBIDDEN, "Les droits accordes depassent ceux de l'invitant.")
    if body.invitee_email == identity.email:
        raise AppError(ErrorCode.CONFLICT, "On ne peut pas s'inviter soi-meme.")
    existing = db.scalar(
        select(Invitation.id).where(
            Invitation.project_id == project_id,
            Invitation.invitee_email == body.invitee_email,
            Invitation.status == InvitationStatus.SENT.value,
        )
    )
    if existing is not None:
        raise AppError(ErrorCode.CONFLICT, "Une invitation est deja en attente pour cette adresse.")
    invitee_id = await iam.find_user_id_by_email(body.invitee_email)
    if invitee_id and project_id in await iam.list_projects(invitee_id):
        raise AppError(ErrorCode.CONFLICT, "Cet utilisateur est deja membre du projet.")
    row = Invitation(
        project_id=project_id,
        inviter_id=identity.user_id,
        invitee_email=body.invitee_email,
        status=InvitationStatus.SENT.value,
        profile_id=body.profile_id,
        rights_snapshot=sorted(granted),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor_id=identity.user_id,
        action="invitation.sent",
        entity_type="invitation",
        entity_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    if invitee_id:
        await notifications.notify(
            Notification(invitee_id, "Invitation", f"Vous etes invite dans le projet {project.name}.")
        )
    return row


async def list_invitations(
    db: Session, iam: IamPort, identity: Identity, project_id: str, params: PageParams
) -> Page[InvitationOut]:
    """F13 : liste paginee des invitations du projet."""
    _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    statement = (
        select(Invitation)
        .where(Invitation.project_id == project_id)
        .order_by(Invitation.created_at.desc())
    )
    rows, total = paginate(db, statement, params)
    return Page[InvitationOut](
        items=[_out_invitation(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


def _invitation(db: Session, invitation_id: int) -> Invitation:
    row = db.get(Invitation, invitation_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Invitation introuvable.")
    return row


def _require_sent(row: Invitation) -> None:
    if row.status != InvitationStatus.SENT.value:
        raise AppError(ErrorCode.INVALID_STATE, "Cette invitation n'est plus en attente.")


async def accept_invitation(
    db: Session, iam: IamPort, identity: Identity, invitation_id: int
) -> Invitation:
    """F13 : l'invite accepte et devient membre."""
    row = _invitation(db, invitation_id)
    _require_sent(row)
    if identity.email.lower() != row.invitee_email.lower():
        raise AppError(ErrorCode.FORBIDDEN, "Seul l'invite peut accepter cette invitation.")
    await iam.invite_user(identity.user_id, row.project_id, row.rights_snapshot)
    db.add(
        Membership(
            project_id=row.project_id,
            user_id=identity.user_id,
            role=MembershipRole.GUEST.value,
        )
    )
    row.status = InvitationStatus.ACCEPTED.value
    record_audit(
        db,
        actor_id=identity.user_id,
        action="invitation.accepted",
        entity_type="invitation",
        entity_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    return row


def refuse_invitation(db: Session, identity: Identity, invitation_id: int) -> Invitation:
    """F13 : l'invite refuse l'invitation."""
    row = _invitation(db, invitation_id)
    _require_sent(row)
    if identity.email.lower() != row.invitee_email.lower():
        raise AppError(ErrorCode.FORBIDDEN, "Seul l'invite peut refuser cette invitation.")
    row.status = InvitationStatus.REFUSED.value
    record_audit(
        db,
        actor_id=identity.user_id,
        action="invitation.refused",
        entity_type="invitation",
        entity_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    return row


def cancel_invitation(db: Session, identity: Identity, invitation_id: int) -> Invitation:
    """F13 : l'auteur ou le proprietaire annule une invitation non acceptee."""
    row = _invitation(db, invitation_id)
    _require_sent(row)
    project = _project(db, row.project_id)
    if identity.user_id != row.inviter_id and identity.user_id != project.owner_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul l'auteur ou le proprietaire peut annuler.")
    row.status = InvitationStatus.CANCELLED.value
    record_audit(
        db,
        actor_id=identity.user_id,
        action="invitation.cancelled",
        entity_type="invitation",
        entity_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    return row
