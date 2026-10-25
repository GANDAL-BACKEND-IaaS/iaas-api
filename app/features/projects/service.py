"""Projets, membres et invitations.

La table projects et le port IAM partagent le meme identifiant de projet.
La propriete ne se transfere pas. L'IAM est rehydrate depuis ces tables au demarrage ;
les droits effectifs d'un invite sont l'union de son profil et de ses droits additionnels.
"""

import logging

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.ports.dns import DnsPort, DnsUnavailable
from app.application.ports.hypervisor import HypervisorPort, HypervisorUnavailable, VmRef
from app.application.ports.iam import (
    AlreadyMember,
    GlobalRole,
    IamPort,
    Identity,
    NotAMember,
    OwnerRightsImmutable,
    ProjectAlreadyExists,
    UserNotFound,
)
from app.application.ports.network import NetworkPort, NetworkRef, NetworkUnavailable
from app.application.ports.notifications import Notification, NotificationsPort
from app.application.ports.storage import StoragePort, StorageUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import Page, PageParams, paginate
from app.features.profiles.service import ProfileNotFound, UnknownRights, resolve_rights
from app.features.projects.schemas import (
    InvitationCreateIn,
    InvitationOut,
    MemberRightsUpdateIn,
    ProjectMemberOut,
    ProjectOut,
)
from app.features.shares.service import revoke_received_by_project
from app.features.storages.service import delete_storage_infrastructure
from app.features.vms.service import delete_vm_infrastructure
from app.shared.deletion import DeletionOut, DeletionPreviewOut, expected_text, is_confirmed
from app.shared.enums import (
    InvitationStatus,
    MembershipRole,
    RequestStatus,
    ResourceType,
    ShareStatus,
)
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.projects import Invitation, Membership, Project
from app.shared.models.requests import ResourceRequest
from app.shared.models.rights import RightModel
from app.shared.models.shares import ResourceShare
from app.shared.models.storages import Storage
from app.shared.models.vms import Vm
from app.shared.policies.rights import membership_rights
from app.shared.time import utcnow

logger = logging.getLogger(__name__)


def _project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


async def _must_be_member(iam: IamPort, user_id: str, project_id: str) -> None:
    if project_id not in await iam.list_projects(user_id):
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur n'est pas membre du projet.")


def _project_out(project: Project, user_id: str) -> ProjectOut:
    role = MembershipRole.OWNER if project.owner_id == user_id else MembershipRole.GUEST
    return ProjectOut(
        id=project.id,
        name=project.name,
        owner_id=project.owner_id,
        current_user_role=role,
        created_at=project.created_at,
    )


def _ensure_unique_name(
    db: Session, owner_id: str, name: str, exclude_id: str | None = None
) -> None:
    statement = select(Project.id).where(Project.owner_id == owner_id, Project.name == name)
    if exclude_id is not None:
        statement = statement.where(Project.id != exclude_id)
    if db.scalar(statement) is not None:
        raise AppError(ErrorCode.CONFLICT, "Ce nom de projet est deja utilise.")


async def _notify(
    notifications: NotificationsPort, user_id: str, subject: str, message: str
) -> None:
    try:
        await notifications.notify(Notification(user_id=user_id, subject=subject, message=message))
    except Exception:
        logger.warning("Notification non delivree pour %s.", user_id)


async def create_project(
    db: Session, iam: IamPort, identity: Identity, name: str
) -> ProjectOut:
    """F12 : cree un projet dont l'appelant devient proprietaire.

    Un administrateur est un compte a part : il traite les demandes et les packs,
    il ne cree pas de projet.
    """
    if identity.role == GlobalRole.ADMIN:
        raise AppError(
            ErrorCode.FORBIDDEN,
            "Un administrateur ne peut pas creer de projet.",
        )
    _ensure_unique_name(db, identity.user_id, name)
    project = Project(name=name, owner_id=identity.user_id)
    db.add(project)
    db.flush()
    db.add(
        Membership(
            project_id=project.id,
            user_id=identity.user_id,
            role=MembershipRole.OWNER.value,
            additional_rights=[],
        )
    )
    try:
        await iam.create_project(identity.user_id, project.id)
    except ProjectAlreadyExists:
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, "Cet identifiant de projet est deja utilise.") from None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, "Ce nom de projet est deja utilise.") from None
    db.refresh(project)
    record_audit(
        db,
        actor_id=identity.user_id,
        action="project.created",
        entity_type="project",
        entity_id=project.id,
    )
    db.commit()
    return _project_out(project, identity.user_id)


async def list_projects(
    db: Session, iam: IamPort, identity: Identity, params: PageParams
) -> Page[ProjectOut]:
    """F12 : liste paginee des projets de l'appelant, triee par nom."""
    ids = await iam.list_projects(identity.user_id)
    if not ids:
        return Page.build([], 0, params)
    statement = select(Project).where(Project.id.in_(ids)).order_by(Project.name, Project.id)
    rows, total = paginate(db, statement, params)
    return Page.build([_project_out(row, identity.user_id) for row in rows], total, params)


async def get_project(
    db: Session, iam: IamPort, identity: Identity, project_id: str
) -> ProjectOut:
    """F12 : consulte un projet dont l'appelant est membre."""
    project = _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    return _project_out(project, identity.user_id)


async def rename_project(
    db: Session, iam: IamPort, identity: Identity, project_id: str, name: str
) -> ProjectOut:
    """F12 : renomme un projet. Reserve au proprietaire."""
    project = _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    if project.owner_id != identity.user_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul le proprietaire peut renommer le projet.")
    _ensure_unique_name(db, project.owner_id, name, exclude_id=project.id)
    old_name = project.name
    project.name = name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, "Ce nom de projet est deja utilise.") from None
    db.refresh(project)
    record_audit(
        db,
        actor_id=identity.user_id,
        action="project.renamed",
        entity_type="project",
        entity_id=project.id,
        data={"old_name": old_name, "name": name},
    )
    db.commit()
    return _project_out(project, identity.user_id)


async def _delete_project_resources(
    db: Session,
    hypervisor: HypervisorPort,
    network: NetworkPort,
    dns: DnsPort,
    storage: StoragePort,
    *,
    actor_id: str,
    project: Project,
) -> None:
    """Supprime les ressources et dependances locales. N'enregistre pas la transaction."""
    await revoke_received_by_project(
        db, network, actor_id=actor_id, project_id=project.id
    )
    networks = list(db.scalars(select(Network).where(Network.project_id == project.id)))
    for row in networks:
        await network.delete_network(NetworkRef(row.id))
        db.execute(delete(NetworkVm).where(NetworkVm.network_id == row.id))
        db.delete(row)
    vms = list(db.scalars(select(Vm).where(Vm.origin_project_id == project.id)))
    for vm in vms:
        await delete_vm_infrastructure(
            db, hypervisor, network, dns, actor_id=actor_id, vm=vm
        )
    storages = list(db.scalars(select(Storage).where(Storage.origin_project_id == project.id)))
    for row in storages:
        await delete_storage_infrastructure(db, storage, actor_id=actor_id, storage=row)
    db.execute(delete(ResourceRequest).where(ResourceRequest.project_id == project.id))
    db.execute(
        delete(ResourceShare).where(
            or_(
                ResourceShare.origin_project_id == project.id,
                ResourceShare.dest_project_id == project.id,
            )
        )
    )
    db.execute(delete(Invitation).where(Invitation.project_id == project.id))
    db.execute(delete(Membership).where(Membership.project_id == project.id))


async def delete_project(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    network: NetworkPort,
    dns: DnsPort,
    storage: StoragePort,
    identity: Identity,
    project_id: str,
    confirmation_text: str | None,
) -> DeletionPreviewOut | DeletionOut:
    """F12 : protocole de suppression en deux temps, en cascade (R23)."""
    project = _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    if project.owner_id != identity.user_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul le proprietaire peut supprimer le projet.")
    text = expected_text(project.name)
    if not is_confirmed(confirmation_text, text):
        vm_count = len(list(db.scalars(select(Vm.id).where(Vm.origin_project_id == project.id))))
        storage_count = len(
            list(db.scalars(select(Storage.id).where(Storage.origin_project_id == project.id)))
        )
        network_count = len(
            list(db.scalars(select(Network.id).where(Network.project_id == project.id)))
        )
        received = len(
            list(
                db.scalars(
                    select(ResourceShare.id).where(
                        ResourceShare.dest_project_id == project.id,
                        ResourceShare.status == "active",
                    )
                )
            )
        )
        return DeletionPreviewOut(
            confirmation_text=text,
            warning=(
                f"Le projet {project.name} sera supprime avec {vm_count} VM, "
                f"{storage_count} stockage(s) et {network_count} reseau(x). "
                f"{received} partage(s) recu(s) seront revoques. Cette action est irreversible."
            ),
        )
    try:
        await _delete_project_resources(
            db,
            hypervisor,
            network,
            dns,
            storage,
            actor_id=identity.user_id,
            project=project,
        )
    except AppError:
        db.rollback()
        raise
    except (
        NetworkUnavailable,
        DnsUnavailable,
        HypervisorUnavailable,
        StorageUnavailable,
        KeyError,
    ):
        db.rollback()
        raise upstream_unavailable("infrastructure") from None
    record_audit(
        db,
        actor_id=identity.user_id,
        action="project.deleted",
        entity_type="project",
        entity_id=project.id,
    )
    db.delete(project)
    db.commit()
    try:
        await iam.delete_project(project_id)
    except Exception:  # pragma: no cover - le mock IAM ne leve pas
        logger.warning("Projet %s supprime en base mais pas dans l'IAM.", project_id)
    return DeletionOut(
        resource_type="project",
        resource_id=project_id,
        message=f"Le projet {project.name} et ses ressources ont bien ete supprimes.",
    )


async def list_members(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    params: PageParams,
    *,
    role: MembershipRole | None = None,
) -> Page[ProjectMemberOut]:
    """F12 : liste paginee des membres du projet, proprietaire inclus."""
    _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    known = list(db.scalars(select(RightModel.code).order_by(RightModel.code)))
    statement = select(Membership).where(Membership.project_id == project_id)
    if role is not None:
        statement = statement.where(Membership.role == role.value)
    statement = statement.order_by(Membership.role.desc(), Membership.user_id)
    rows, total = paginate(db, statement, params)
    items = [
        ProjectMemberOut(
            user_id=row.user_id,
            role=MembershipRole(row.role),
            profile_id=row.profile_id,
            rights=sorted(membership_rights(row, known)),
            joined_at=row.created_at,
        )
        for row in rows
    ]
    return Page.build(items, total, params)


async def update_member_rights(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    user_id: str,
    body: MemberRightsUpdateIn,
) -> ProjectMemberOut:
    """F12 : remplace le profil et/ou les droits additionnels d'un invite. Proprietaire seulement."""
    project = _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    if project.owner_id != identity.user_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul le proprietaire peut modifier les droits.")
    member = db.scalar(
        select(Membership).where(
            Membership.project_id == project_id, Membership.user_id == user_id
        )
    )
    if member is None:
        raise AppError(ErrorCode.NOT_FOUND, "Membre introuvable.")
    if member.role == MembershipRole.OWNER.value:
        raise AppError(ErrorCode.FORBIDDEN, "Les droits du proprietaire ne sont pas modifiables.")
    fields = body.model_fields_set
    profile_id = body.profile_id if "profile_id" in fields else member.profile_id
    additional = (
        list(body.additional_rights or [])
        if "additional_rights" in fields
        else list(member.additional_rights or [])
    )
    try:
        granted = resolve_rights(db, profile_id, additional)
    except ProfileNotFound:
        raise AppError(ErrorCode.NOT_FOUND, "Profil introuvable.") from None
    except UnknownRights as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Droits inconnus : {exc}.") from None
    try:
        await iam.update_rights(member.user_id, project_id, granted)
    except NotAMember:
        raise AppError(ErrorCode.NOT_FOUND, "Membre introuvable.") from None
    except OwnerRightsImmutable:
        raise AppError(ErrorCode.FORBIDDEN, "Les droits du proprietaire ne sont pas modifiables.") from None
    member.profile_id = profile_id
    member.additional_rights = sorted(set(additional))
    record_audit(
        db,
        actor_id=identity.user_id,
        action="member.rights_updated",
        entity_type="membership",
        entity_id=member.id,
        data={"user_id": member.user_id},
    )
    db.commit()
    db.refresh(member)
    known = list(db.scalars(select(RightModel.code).order_by(RightModel.code)))
    return ProjectMemberOut(
        user_id=member.user_id,
        role=MembershipRole(member.role),
        profile_id=member.profile_id,
        rights=sorted(membership_rights(member, known)),
        joined_at=member.created_at,
    )


async def cleanup_member_contributions(
    db: Session,
    iam: IamPort,
    network: NetworkPort,
    *,
    user_id: str,
    project_id: str,
    actor_id: str,
) -> None:
    """Invalide les contributions du membre dans le projet qu'il quitte.

    Les demandes et invitations en attente sont annulees. Un partage cree par le
    membre est conserve s'il reste membre de l'autre projet concerne ; sinon il est
    revoque (avec detachement reseau pour une VM).
    """
    invitations = list(
        db.scalars(
            select(Invitation).where(
                Invitation.project_id == project_id,
                Invitation.inviter_id == user_id,
                Invitation.status == InvitationStatus.SENT.value,
            )
        )
    )
    for row in invitations:
        row.status = InvitationStatus.CANCELLED.value
        row.updated_at = utcnow()
        record_audit(
            db,
            actor_id=actor_id,
            action="invitation.cancelled",
            entity_type="invitation",
            entity_id=row.id,
            data={"reason": "member_removed", "inviter_id": user_id},
        )

    requests = list(
        db.scalars(
            select(ResourceRequest).where(
                ResourceRequest.project_id == project_id,
                ResourceRequest.author_id == user_id,
                ResourceRequest.status == RequestStatus.PENDING.value,
            )
        )
    )
    for row in requests:
        row.status = RequestStatus.CANCELLED.value
        row.updated_at = utcnow()
        record_audit(
            db,
            actor_id=actor_id,
            action="request.cancelled",
            entity_type="request",
            entity_id=row.id,
            data={"reason": "member_removed", "author_id": user_id},
        )

    shares = list(
        db.scalars(
            select(ResourceShare).where(
                ResourceShare.created_by == user_id,
                ResourceShare.status == ShareStatus.ACTIVE.value,
                or_(
                    ResourceShare.origin_project_id == project_id,
                    ResourceShare.dest_project_id == project_id,
                ),
            )
        )
    )
    if not shares:
        return
    projects = await iam.list_projects(user_id)
    for row in shares:
        other = (
            row.dest_project_id
            if row.origin_project_id == project_id
            else row.origin_project_id
        )
        if other in projects:
            continue
        if row.resource_type == ResourceType.VM.value:
            try:
                await network.detach_vm_from_project(VmRef(row.resource_id), row.dest_project_id)
            except NetworkUnavailable:
                raise upstream_unavailable("Reseau") from None
            network_ids = select(Network.id).where(Network.project_id == row.dest_project_id)
            db.execute(
                delete(NetworkVm).where(
                    NetworkVm.vm_id == row.resource_id,
                    NetworkVm.network_id.in_(network_ids),
                )
            )
        row.status = ShareStatus.REVOKED.value
        record_audit(
            db,
            actor_id=actor_id,
            action="share.revoked",
            entity_type="share",
            entity_id=row.id,
            data={"reason": "member_removed", "creator_id": user_id},
        )


async def remove_member(
    db: Session,
    iam: IamPort,
    network: NetworkPort,
    identity: Identity,
    project_id: str,
    user_id: str,
) -> None:
    """F12 : retire un invite. Le proprietaire ne peut pas etre retire."""
    project = _project(db, project_id)
    await _must_be_member(iam, identity.user_id, project_id)
    if project.owner_id != identity.user_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul le proprietaire peut retirer un membre.")
    member = db.scalar(
        select(Membership).where(
            Membership.project_id == project_id, Membership.user_id == user_id
        )
    )
    if member is None:
        raise AppError(ErrorCode.NOT_FOUND, "Membre introuvable.")
    if member.role == MembershipRole.OWNER.value:
        raise AppError(ErrorCode.INVALID_STATE, "Le proprietaire ne peut pas etre retire.")
    try:
        await cleanup_member_contributions(
            db,
            iam,
            network,
            user_id=user_id,
            project_id=project_id,
            actor_id=identity.user_id,
        )
        await iam.remove_member(user_id, project_id)
    except NotAMember:
        pass
    except OwnerRightsImmutable:
        db.rollback()
        raise AppError(ErrorCode.INVALID_STATE, "Le proprietaire ne peut pas etre retire.") from None
    except AppError:
        db.rollback()
        raise
    db.delete(member)
    record_audit(
        db,
        actor_id=identity.user_id,
        action="member.removed",
        entity_type="membership",
        entity_id=member.id,
        data={"user_id": user_id},
    )
    db.commit()


def _invitation_out(row: Invitation) -> InvitationOut:
    return InvitationOut(
        id=row.id,
        project_id=row.project_id,
        project_name=row.project.name,
        inviter_id=row.inviter_id,
        invitee_id=row.invitee_id,
        invitee_email=row.invitee_email,
        status=InvitationStatus(row.status),
        profile_id=row.profile_id,
        additional_rights=sorted(row.additional_rights or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _require_invite_right(iam: IamPort, user_id: str, project_id: str) -> None:
    if project_id not in await iam.list_projects(user_id):
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur n'est pas membre du projet.")
    rights = await iam.get_rights(user_id, project_id)
    if "project.invite" not in rights:
        raise AppError(ErrorCode.FORBIDDEN, "Droit requis manquant : project.invite.")


async def _resolve_invitee(iam: IamPort, body: InvitationCreateIn) -> Identity:
    """Resout l'invite par identifiant IAM ou par email, sans exposer d'annuaire."""
    if body.invitee_id is not None:
        try:
            return await iam.get_user(body.invitee_id)
        except UserNotFound:
            raise AppError(ErrorCode.NOT_FOUND, "Utilisateur invite introuvable.") from None

    assert body.email is not None
    user_id = await iam.find_user_id_by_email(body.email)
    if user_id is None:
        raise AppError(ErrorCode.NOT_FOUND, "Utilisateur invite introuvable.")
    try:
        return await iam.get_user(user_id)
    except UserNotFound:
        raise AppError(ErrorCode.NOT_FOUND, "Utilisateur invite introuvable.") from None


async def create_invitation(
    db: Session,
    iam: IamPort,
    notifications: NotificationsPort,
    identity: Identity,
    project_id: str,
    body: InvitationCreateIn,
) -> InvitationOut:
    """F13 : invite un utilisateur. Les droits d'un invite sont plafonnes aux siens (R8)."""
    project = _project(db, project_id)
    await _require_invite_right(iam, identity.user_id, project_id)
    invitee = await _resolve_invitee(iam, body)
    if invitee.user_id == identity.user_id:
        raise AppError(ErrorCode.CONFLICT, "On ne peut pas s'inviter soi-meme.")
    already = db.scalar(
        select(Membership.id).where(
            Membership.project_id == project_id, Membership.user_id == invitee.user_id
        )
    )
    if already is not None:
        raise AppError(ErrorCode.CONFLICT, "Cet utilisateur est deja membre du projet.")
    try:
        granted = resolve_rights(db, body.profile_id, body.additional_rights)
    except ProfileNotFound:
        raise AppError(ErrorCode.NOT_FOUND, "Profil introuvable.") from None
    except UnknownRights as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Droits inconnus : {exc}.") from None
    if project.owner_id != identity.user_id:
        inviter_rights = await iam.get_rights(identity.user_id, project_id)
        if not granted <= inviter_rights:
            raise AppError(ErrorCode.FORBIDDEN, "Les droits accordes depassent ceux de l'invitant.")
    pending = db.scalar(
        select(Invitation.id).where(
            Invitation.project_id == project_id,
            Invitation.invitee_id == invitee.user_id,
            Invitation.status == InvitationStatus.SENT.value,
        )
    )
    if pending is not None:
        raise AppError(ErrorCode.CONFLICT, "Une invitation est deja en attente pour cet utilisateur.")
    row = Invitation(
        project_id=project_id,
        inviter_id=identity.user_id,
        invitee_id=invitee.user_id,
        invitee_email=invitee.email,
        status=InvitationStatus.SENT.value,
        profile_id=body.profile_id,
        additional_rights=sorted(set(body.additional_rights)),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor_id=identity.user_id,
        action="invitation.sent",
        entity_type="invitation",
        entity_id=row.id,
        data={"invitee_id": invitee.user_id, "invitee_email": invitee.email},
    )
    db.commit()
    db.refresh(row)
    await _notify(
        notifications,
        invitee.user_id,
        "Invitation",
        f"Vous etes invite dans le projet {project.name}.",
    )
    return _invitation_out(row)


async def list_project_invitations(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    params: PageParams,
    *,
    status: InvitationStatus | None = None,
    invitee_id: str | None = None,
) -> Page[InvitationOut]:
    """F13 : liste paginee des invitations du projet."""
    _project(db, project_id)
    await _require_invite_right(iam, identity.user_id, project_id)
    statement = select(Invitation).where(Invitation.project_id == project_id)
    if status is not None:
        statement = statement.where(Invitation.status == status.value)
    if invitee_id is not None:
        statement = statement.where(Invitation.invitee_id == invitee_id)
    statement = statement.order_by(Invitation.created_at.desc(), Invitation.id.desc())
    rows, total = paginate(db, statement, params)
    return Page.build([_invitation_out(row) for row in rows], total, params)


def list_my_invitations(
    db: Session,
    identity: Identity,
    params: PageParams,
    *,
    status: InvitationStatus | None = None,
) -> Page[InvitationOut]:
    """F13 : invitations recues par l'appelant, triees de la plus recente a la plus ancienne."""
    statement = select(Invitation).where(Invitation.invitee_id == identity.user_id)
    if status is not None:
        statement = statement.where(Invitation.status == status.value)
    statement = statement.order_by(Invitation.created_at.desc(), Invitation.id.desc())
    rows, total = paginate(db, statement, params)
    return Page.build([_invitation_out(row) for row in rows], total, params)


def _invitation(db: Session, invitation_id: str) -> Invitation:
    row = db.get(Invitation, invitation_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Invitation introuvable.")
    return row


def _require_sent(row: Invitation) -> None:
    if row.status != InvitationStatus.SENT.value:
        raise AppError(ErrorCode.INVALID_STATE, "Cette invitation n'est plus en attente.")


async def accept_invitation(
    db: Session, iam: IamPort, identity: Identity, invitation_id: str
) -> InvitationOut:
    """F13 : l'invite accepte et devient membre avec le profil et les droits prevus."""
    row = _invitation(db, invitation_id)
    _require_sent(row)
    if identity.user_id != row.invitee_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul l'invite peut accepter cette invitation.")
    exists = db.scalar(
        select(Membership.id).where(
            Membership.project_id == row.project_id, Membership.user_id == identity.user_id
        )
    )
    if exists is not None:
        raise AppError(ErrorCode.CONFLICT, "Cet utilisateur est deja membre du projet.")
    try:
        granted = resolve_rights(db, row.profile_id, row.additional_rights)
    except ProfileNotFound:
        raise AppError(ErrorCode.NOT_FOUND, "Profil introuvable.") from None
    except UnknownRights as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, f"Droits inconnus : {exc}.") from None
    try:
        await iam.invite_user(identity.user_id, row.project_id, granted)
    except AlreadyMember:
        raise AppError(ErrorCode.CONFLICT, "Cet utilisateur est deja membre du projet.") from None
    db.add(
        Membership(
            project_id=row.project_id,
            user_id=identity.user_id,
            role=MembershipRole.GUEST.value,
            profile_id=row.profile_id,
            additional_rights=sorted(set(row.additional_rights or [])),
        )
    )
    row.status = InvitationStatus.ACCEPTED.value
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=identity.user_id,
        action="invitation.accepted",
        entity_type="invitation",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return _invitation_out(row)


def refuse_invitation(db: Session, identity: Identity, invitation_id: str) -> InvitationOut:
    """F13 : l'invite refuse l'invitation."""
    row = _invitation(db, invitation_id)
    _require_sent(row)
    if identity.user_id != row.invitee_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul l'invite peut refuser cette invitation.")
    row.status = InvitationStatus.REFUSED.value
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=identity.user_id,
        action="invitation.refused",
        entity_type="invitation",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return _invitation_out(row)


async def cancel_invitation(
    db: Session, iam: IamPort, identity: Identity, invitation_id: str
) -> InvitationOut:
    """F13 : l'auteur ou le proprietaire annule une invitation non acceptee (R9).

    L'appelant doit encore etre membre du projet : un invitant retire ne peut plus
    agir sur les invitations qu'il avait envoyees.
    """
    row = _invitation(db, invitation_id)
    await _must_be_member(iam, identity.user_id, row.project_id)
    _require_sent(row)
    project = _project(db, row.project_id)
    if identity.user_id != row.inviter_id and identity.user_id != project.owner_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul l'auteur ou le proprietaire peut annuler.")
    row.status = InvitationStatus.CANCELLED.value
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=identity.user_id,
        action="invitation.cancelled",
        entity_type="invitation",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return _invitation_out(row)
