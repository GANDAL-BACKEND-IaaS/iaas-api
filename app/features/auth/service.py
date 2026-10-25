"""Services d'identite : reference locale et suppression de compte."""

import logging

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.ports.dns import DnsPort, DnsUnavailable
from app.application.ports.hypervisor import HypervisorPort, HypervisorUnavailable
from app.application.ports.iam import (
    GlobalRole,
    IamError,
    IamPort,
    Identity,
    NotAMember,
    UserNotFound,
)
from app.application.ports.network import NetworkPort, NetworkUnavailable
from app.application.ports.storage import StoragePort, StorageUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, upstream_unavailable
from app.features.projects.service import (
    _delete_project_resources,
    cleanup_member_contributions,
)
from app.shared.enums import InvitationStatus
from app.shared.models.identities import AdminRef, UserRef
from app.shared.models.projects import Invitation, Membership, Project
from app.shared.time import utcnow

logger = logging.getLogger(__name__)


def ensure_reference(db: Session, identity: Identity) -> None:
    """Crée la référence locale à la première connexion (idempotent)."""
    model = AdminRef if identity.role == GlobalRole.ADMIN else UserRef
    if db.get(model, identity.user_id) is None:
        db.add(model(id=identity.user_id))
        db.commit()


async def delete_account_cascade(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    network: NetworkPort,
    dns: DnsPort,
    storage: StoragePort,
    identity: Identity,
) -> None:
    """Supprime les projets possedes puis nettoie les appartenances et contributions.

    Les effets externes sont executes avant le commit local. En cas d'echec, tout
    est annule et le compte reste utilisable. Le compte IAM n'est supprime qu'apres
    le commit local, afin de pouvoir rejouer l'operation si l'IAM echoue.
    """
    owned = list(db.scalars(select(Project).where(Project.owner_id == identity.user_id)))
    owned_ids = [project.id for project in owned]

    try:
        for project in owned:
            await _delete_project_resources(
                db,
                hypervisor,
                network,
                dns,
                storage,
                actor_id=identity.user_id,
                project=project,
            )
            record_audit(
                db,
                actor_id=identity.user_id,
                action="project.deleted",
                entity_type="project",
                entity_id=project.id,
                data={"reason": "account_deleted"},
            )
            db.delete(project)

        memberships = list(
            db.scalars(select(Membership).where(Membership.user_id == identity.user_id))
        )
        for member in memberships:
            await cleanup_member_contributions(
                db,
                iam,
                network,
                user_id=identity.user_id,
                project_id=member.project_id,
                actor_id=identity.user_id,
            )
            try:
                await iam.remove_member(identity.user_id, member.project_id)
            except NotAMember:
                pass
            db.delete(member)

        invitations = list(
            db.scalars(
                select(Invitation).where(
                    or_(
                        Invitation.inviter_id == identity.user_id,
                        Invitation.invitee_id == identity.user_id,
                    ),
                    Invitation.status == InvitationStatus.SENT.value,
                )
            )
        )
        for row in invitations:
            row.status = InvitationStatus.CANCELLED.value
            row.updated_at = utcnow()
            record_audit(
                db,
                actor_id=identity.user_id,
                action="invitation.cancelled",
                entity_type="invitation",
                entity_id=row.id,
                data={"reason": "account_deleted"},
            )

        for model in (UserRef, AdminRef):
            obj = db.get(model, identity.user_id)
            if obj is not None:
                db.delete(obj)
        record_audit(
            db,
            actor_id=identity.user_id,
            action="account.deleted",
            entity_type="identity",
            entity_id=identity.user_id,
        )
        db.commit()
    except AppError:
        db.rollback()
        raise
    except (NetworkUnavailable, DnsUnavailable, HypervisorUnavailable, StorageUnavailable, KeyError):
        db.rollback()
        raise upstream_unavailable("infrastructure") from None
    except IamError:
        db.rollback()
        raise upstream_unavailable("IAM") from None

    for project_id in owned_ids:
        try:
            await iam.delete_project(project_id)
        except Exception:  # pragma: no cover - le mock IAM ne leve pas
            logger.warning("Projet %s supprime en base mais pas dans l'IAM.", project_id)
    try:
        await iam.delete_account(identity.user_id)
    except UserNotFound:
        raise
    except IamError:
        raise upstream_unavailable("IAM") from None
