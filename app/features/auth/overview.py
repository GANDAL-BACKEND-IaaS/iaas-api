"""Assemblage des donnees operationnelles d'un compte pour l'administration."""

from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.ports.iam import IamError, IamPort, UserNotFound
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.features.auth.overview_schemas import UserOverviewOut, UserProjectOverviewOut
from app.features.networks.schemas import NetworkOut
from app.features.projects.schemas import InvitationOut
from app.features.requests.schemas import RequestOut
from app.features.shares.schemas import ShareOut
from app.features.vms.schemas import VMOut
from app.shared.enums import MembershipRole, ResourceType, ShareStatus
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.projects import Invitation, Membership, Project
from app.shared.models.requests import ResourceRequest
from app.shared.models.rights import RightModel
from app.shared.models.shares import ResourceShare
from app.shared.models.vms import Vm
from app.shared.policies.rights import membership_rights


async def get_user_overview(db: Session, iam: IamPort, user_id: str) -> UserOverviewOut:
    """Retourne les projets, ressources et relations operationnelles d'un compte."""
    try:
        await iam.get_user(user_id)
    except UserNotFound:
        raise AppError(ErrorCode.NOT_FOUND, "Utilisateur introuvable dans l'IAM.") from None
    except IamError:
        raise upstream_unavailable("IAM") from None

    memberships = list(
        db.scalars(
            select(Membership)
            .where(Membership.user_id == user_id)
            .order_by(Membership.project_id)
        )
    )
    membership_by_project = {membership.project_id: membership for membership in memberships}
    projects = list(
        db.scalars(
            select(Project)
            .where(
                or_(
                    Project.owner_id == user_id,
                    Project.id.in_(membership_by_project) if membership_by_project else False,
                )
            )
            .order_by(Project.name, Project.id)
        )
    )
    project_ids = {project.id for project in projects}
    known_rights = frozenset(db.scalars(select(RightModel.code)))

    shares = list(
        db.scalars(
            select(ResourceShare)
            .where(
                or_(
                    ResourceShare.created_by == user_id,
                    ResourceShare.origin_project_id.in_(project_ids) if project_ids else False,
                    ResourceShare.dest_project_id.in_(project_ids) if project_ids else False,
                )
            )
            .order_by(ResourceShare.created_at.desc(), ResourceShare.id)
        )
    )
    shared_destinations: dict[str, set[str]] = defaultdict(set)
    for share in shares:
        if (
            share.resource_type == ResourceType.VM.value
            and share.status == ShareStatus.ACTIVE.value
            and share.dest_project_id in project_ids
        ):
            shared_destinations[share.resource_id].add(share.dest_project_id)

    visible_vm_ids = select(ResourceShare.resource_id).where(
        ResourceShare.resource_type == ResourceType.VM.value,
        ResourceShare.status == ShareStatus.ACTIVE.value,
        ResourceShare.dest_project_id.in_(project_ids) if project_ids else False,
    )
    vms = list(
        db.scalars(
            select(Vm)
            .where(or_(Vm.origin_project_id.in_(project_ids) if project_ids else False, Vm.id.in_(visible_vm_ids)))
            .order_by(Vm.name, Vm.id)
        )
    )
    vms_by_project: dict[str, list[VMOut]] = defaultdict(list)
    for vm in vms:
        if vm.origin_project_id in project_ids:
            vms_by_project[vm.origin_project_id].append(
                VMOut.model_validate(vm).model_copy(update={"shared": False})
            )
        for project_id in sorted(shared_destinations.get(vm.id, ())):
            vms_by_project[project_id].append(
                VMOut.model_validate(vm).model_copy(update={"shared": True})
            )

    networks = list(
        db.scalars(
            select(Network)
            .where(Network.project_id.in_(project_ids) if project_ids else False)
            .order_by(Network.name, Network.id)
        )
    )
    network_ids = {network.id for network in networks}
    vm_ids_by_network: dict[str, list[str]] = defaultdict(list)
    if network_ids:
        links = db.execute(
            select(NetworkVm.network_id, NetworkVm.vm_id)
            .where(NetworkVm.network_id.in_(network_ids))
            .order_by(NetworkVm.network_id, NetworkVm.vm_id)
        )
        for network_id, vm_id in links:
            vm_ids_by_network[network_id].append(vm_id)

    networks_by_project: dict[str, list[NetworkOut]] = defaultdict(list)
    for network in networks:
        networks_by_project[network.project_id].append(
            NetworkOut(
                id=network.id,
                project_id=network.project_id,
                name=network.name,
                vm_ids=vm_ids_by_network[network.id],
                created_at=network.created_at,
            )
        )

    project_overviews = []
    for project in projects:
        membership = membership_by_project.get(project.id)
        role = (
            MembershipRole.OWNER
            if project.owner_id == user_id
            else MembershipRole(membership.role)
        )
        rights = (
            sorted(known_rights)
            if membership is None and role == MembershipRole.OWNER
            else sorted(membership_rights(membership, known_rights))
        )
        project_overviews.append(
            UserProjectOverviewOut(
                id=project.id,
                name=project.name,
                owner_id=project.owner_id,
                role=role,
                rights=rights,
                created_at=project.created_at,
                vms=vms_by_project[project.id],
                networks=networks_by_project[project.id],
            )
        )

    invitations = [
        InvitationOut(
            id=invitation.id,
            project_id=invitation.project_id,
            project_name=project_name,
            inviter_id=invitation.inviter_id,
            invitee_id=invitation.invitee_id,
            invitee_email=invitation.invitee_email,
            status=invitation.status,
            profile_id=invitation.profile_id,
            additional_rights=sorted(invitation.additional_rights or []),
            created_at=invitation.created_at,
            updated_at=invitation.updated_at,
        )
        for invitation, project_name in db.execute(
            select(Invitation, Project.name)
            .join(Project, Project.id == Invitation.project_id)
            .where(or_(Invitation.inviter_id == user_id, Invitation.invitee_id == user_id))
            .order_by(Invitation.created_at.desc(), Invitation.id)
        )
    ]
    requests = list(
        db.scalars(
            select(ResourceRequest)
            .where(ResourceRequest.author_id == user_id)
            .order_by(ResourceRequest.created_at.desc(), ResourceRequest.id)
        )
    )

    return UserOverviewOut(
        projects=project_overviews,
        invitations=invitations,
        requests=[RequestOut.model_validate(request) for request in requests],
        shares=[ShareOut.model_validate(share) for share in shares],
    )
