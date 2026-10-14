"""Moteur des partages entre projets d'un meme proprietaire (section 4.6, R15 a R21).

La creation n'appelle aucun groupe externe. Le retrait d'une VM en reseau appelle le port Reseau.
Un partage revoque n'est pas reactive : il faut en creer un nouveau.
"""

from sqlalchemy import delete, false, or_, select
from sqlalchemy.orm import Session

from app.application.ports.hypervisor import VmRef
from app.application.ports.iam import GlobalRole, IamPort
from app.application.ports.network import NetworkPort, NetworkUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import PageParams, paginate
from app.shared.enums import ResourceType, ShareStatus, StorageState, VmState
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.projects import Project
from app.shared.models.shares import ResourceShare
from app.shared.models.storages import Storage
from app.shared.models.vms import Vm
from app.shared.policies.visibility import is_resource_visible

_RIGHT = {ResourceType.VM: "vm.share", ResourceType.STORAGE: "storage.share"}


def visible_in_project(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
    origin_project_id: str,
    project_id: str,
) -> bool:
    """Helper de visibilite utilise par la politique d'acces et les services."""
    return is_resource_visible(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        origin_project_id=origin_project_id,
        project_id=project_id,
    )


def _project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


def _load_resource(db: Session, resource_type: ResourceType, resource_id: str) -> Vm | Storage:
    if resource_type == ResourceType.VM:
        resource = db.get(Vm, resource_id)
        missing = "VM introuvable."
        deleting = VmState.DELETING.value
    else:
        resource = db.get(Storage, resource_id)
        missing = "Stockage introuvable."
        deleting = StorageState.DELETING.value
    if resource is None:
        raise AppError(ErrorCode.NOT_FOUND, missing)
    if resource.state == deleting:
        raise AppError(ErrorCode.INVALID_STATE, "La ressource est en cours de suppression.")
    return resource


async def create_share(
    db: Session,
    iam: IamPort,
    *,
    user_id: str,
    resource_type: ResourceType,
    resource_id: str,
    dest_project_id: str,
) -> ResourceShare:
    """Rend la ressource visible dans le projet destinataire. Aucun droit n'est transmis (R16)."""
    resource = _load_resource(db, resource_type, resource_id)
    origin = _project(db, resource.origin_project_id)
    dest = _project(db, dest_project_id)
    if origin.id == dest.id:
        raise AppError(
            ErrorCode.CONFLICT,
            "Le projet destinataire doit etre different du projet d'origine.",
        )
    if origin.owner_id != dest.owner_id:
        raise AppError(
            ErrorCode.FORBIDDEN,
            "Le partage n'est possible qu'entre projets d'un meme proprietaire.",
        )
    membership = await iam.list_projects(user_id)
    if origin.id not in membership:
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur n'est pas membre du projet d'origine.")
    rights = await iam.get_rights(user_id, origin.id)
    if _RIGHT[resource_type] not in rights:
        raise AppError(ErrorCode.FORBIDDEN, f"Droit requis manquant : {_RIGHT[resource_type]}.")
    if dest.id not in membership:
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur doit etre membre du projet destinataire.")
    existing = db.scalar(
        select(ResourceShare.id).where(
            ResourceShare.resource_type == resource_type.value,
            ResourceShare.resource_id == resource_id,
            ResourceShare.dest_project_id == dest.id,
            ResourceShare.status == ShareStatus.ACTIVE.value,
        )
    )
    if existing is not None:
        raise AppError(ErrorCode.CONFLICT, "Un partage actif existe deja vers ce projet.")
    row = ResourceShare(
        resource_type=resource_type.value,
        resource_id=resource_id,
        origin_project_id=origin.id,
        dest_project_id=dest.id,
        created_by=user_id,
        status=ShareStatus.ACTIVE.value,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor_id=user_id,
        action="share.created",
        entity_type="share",
        entity_id=str(row.id),
        data={"resource_type": resource_type.value, "resource_id": resource_id},
    )
    db.commit()
    db.refresh(row)
    return row


def _drop_dest_links(db: Session, vm_id: str, dest_project_id: str) -> None:
    network_ids = select(Network.id).where(Network.project_id == dest_project_id)
    db.execute(delete(NetworkVm).where(NetworkVm.vm_id == vm_id, NetworkVm.network_id.in_(network_ids)))


async def revoke_share(
    db: Session,
    network: NetworkPort,
    *,
    user_id: str,
    share_id: int,
) -> ResourceShare:
    """Retire un partage actif. Une VM quitte les reseaux du projet destinataire (R21)."""
    row = db.get(ResourceShare, share_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Partage introuvable.")
    if row.status != ShareStatus.ACTIVE.value:
        raise AppError(ErrorCode.INVALID_STATE, "Un partage revoque n'est pas reactive et ne se retire plus.")
    origin = _project(db, row.origin_project_id)
    if user_id != origin.owner_id and user_id != row.created_by:
        raise AppError(
            ErrorCode.FORBIDDEN,
            "Seul le proprietaire ou l'auteur du partage peut le retirer.",
        )
    if row.resource_type == ResourceType.VM.value:
        try:
            await network.detach_vm_from_project(VmRef(row.resource_id), row.dest_project_id)
        except NetworkUnavailable:
            raise upstream_unavailable("Reseau") from None
        _drop_dest_links(db, row.resource_id, row.dest_project_id)
    row.status = ShareStatus.REVOKED.value
    record_audit(
        db,
        actor_id=user_id,
        action="share.revoked",
        entity_type="share",
        entity_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    return row


async def _can_see(iam: IamPort, actor_id: str, actor_role: GlobalRole, row: ResourceShare) -> bool:
    if actor_role == GlobalRole.ADMIN:
        return True
    projects = await iam.list_projects(actor_id)
    return row.origin_project_id in projects or row.dest_project_id in projects


async def get_share(
    db: Session,
    iam: IamPort,
    *,
    actor_id: str,
    actor_role: GlobalRole,
    share_id: int,
) -> ResourceShare:
    """Retourne un partage visible par un membre des projets concernes."""
    row = db.get(ResourceShare, share_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Partage introuvable.")
    if not await _can_see(iam, actor_id, actor_role, row):
        raise AppError(ErrorCode.FORBIDDEN, "Ce partage ne vous est pas accessible.")
    return row


async def list_shares(
    db: Session,
    iam: IamPort,
    *,
    actor_id: str,
    actor_role: GlobalRole,
    params: PageParams,
) -> tuple[list[ResourceShare], int]:
    """Liste paginee des partages accessibles a l'appelant."""
    statement = select(ResourceShare).order_by(ResourceShare.created_at.desc())
    if actor_role != GlobalRole.ADMIN:
        projects = await iam.list_projects(actor_id)
        if not projects:
            statement = statement.where(false())
        else:
            statement = statement.where(
                or_(
                    ResourceShare.origin_project_id.in_(projects),
                    ResourceShare.dest_project_id.in_(projects),
                )
            )
    rows, total = paginate(db, statement, params)
    return list(rows), total
