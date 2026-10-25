"""Moteur des partages entre projets d'un meme proprietaire (section 4.6, R15 a R21).

La creation n'appelle aucun groupe externe. Le retrait d'une VM en reseau appelle le port Reseau.
Un partage revoque n'est pas reactive : il faut en creer un nouveau.
Un administrateur global ne voit pas les partages des utilisateurs : seul le membership compte.
"""

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.application.ports.hypervisor import VmRef
from app.application.ports.iam import IamPort
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
from app.shared.policies.access import ResourceView, authorize
from app.shared.policies.visibility import is_resource_visible

_RIGHT = {ResourceType.VM: "vm.share", ResourceType.STORAGE: "storage.share"}
_VIEW_RIGHT = {ResourceType.VM: "vm.view", ResourceType.STORAGE: "storage.view"}


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


async def _member(iam: IamPort, user_id: str, project_id: str) -> bool:
    return project_id in await iam.list_projects(user_id)


async def create_share(
    db: Session,
    iam: IamPort,
    *,
    user_id: str,
    project_id: str,
    resource_type: ResourceType,
    resource_id: str,
    dest_project_id: str,
) -> ResourceShare:
    """Rend la ressource visible dans le projet destinataire. Aucun droit n'est transmis (R16)."""
    _project(db, project_id)
    resource = _load_resource(db, resource_type, resource_id)
    if resource.origin_project_id != project_id:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            "La ressource n'appartient pas au projet d'origine indique.",
            details={"origin_project_id": resource.origin_project_id},
        )
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
    await authorize(
        iam=iam,
        db=db,
        user_id=user_id,
        project_id=origin.id,
        required_right=_RIGHT[resource_type],
        resource=ResourceView(resource_type.value, resource_id, origin.id),
    )
    if not await _member(iam, user_id, dest.id):
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
        entity_id=row.id,
        data={"resource_type": resource_type.value, "resource_id": resource_id},
    )
    db.commit()
    db.refresh(row)
    return row


async def list_received(
    db: Session,
    iam: IamPort,
    *,
    user_id: str,
    project_id: str,
    params: PageParams,
    resource_type: ResourceType | None = None,
    status: ShareStatus = ShareStatus.ACTIVE,
) -> tuple[list[ResourceShare], int]:
    """Partages recus par un projet. Le droit de lecture du type est exige."""
    _project(db, project_id)
    if not await _member(iam, user_id, project_id):
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur n'est pas membre du projet.")
    rights = await iam.get_rights(user_id, project_id)
    statement = select(ResourceShare).where(ResourceShare.dest_project_id == project_id)
    if resource_type is not None:
        if _VIEW_RIGHT[resource_type] not in rights:
            raise AppError(
                ErrorCode.FORBIDDEN,
                f"Droit requis manquant : {_VIEW_RIGHT[resource_type]}.",
            )
        statement = statement.where(ResourceShare.resource_type == resource_type.value)
    else:
        visible_types = [
            resource.value
            for resource, right in _VIEW_RIGHT.items()
            if right in rights
        ]
        if not visible_types:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Droit requis manquant : vm.view ou storage.view.",
            )
        statement = statement.where(ResourceShare.resource_type.in_(visible_types))
    statement = statement.where(ResourceShare.status == status.value)
    rows, total = paginate(db, statement.order_by(ResourceShare.created_at.desc()), params)
    return list(rows), total


async def list_for_resource(
    db: Session,
    iam: IamPort,
    *,
    user_id: str,
    project_id: str,
    resource_type: ResourceType,
    resource_id: str,
    params: PageParams,
    status: ShareStatus | None = None,
    dest_project_id: str | None = None,
) -> tuple[list[ResourceShare], int]:
    """Partages emis pour une ressource de ce projet."""
    _project(db, project_id)
    resource = _load_resource(db, resource_type, resource_id)
    if resource.origin_project_id != project_id:
        raise AppError(ErrorCode.NOT_FOUND, "Ressource introuvable dans ce projet.")
    await authorize(
        iam=iam,
        db=db,
        user_id=user_id,
        project_id=project_id,
        required_right=_VIEW_RIGHT[resource_type],
        resource=ResourceView(resource_type.value, resource_id, project_id),
    )
    statement = select(ResourceShare).where(
        ResourceShare.resource_type == resource_type.value,
        ResourceShare.resource_id == resource_id,
    )
    if status is not None:
        statement = statement.where(ResourceShare.status == status.value)
    if dest_project_id is not None:
        statement = statement.where(ResourceShare.dest_project_id == dest_project_id)
    rows, total = paginate(db, statement.order_by(ResourceShare.created_at.desc()), params)
    return list(rows), total


def _drop_dest_links(db: Session, vm_id: str, dest_project_id: str) -> None:
    network_ids = select(Network.id).where(Network.project_id == dest_project_id)
    db.execute(delete(NetworkVm).where(NetworkVm.vm_id == vm_id, NetworkVm.network_id.in_(network_ids)))


async def revoke_all_for_resource(
    db: Session,
    network: NetworkPort | None,
    *,
    actor_id: str,
    resource_type: str,
    resource_id: str,
) -> list[ResourceShare]:
    """Revoque tous les partages actifs d'une ressource. N'enregistre pas la transaction.

    `network` n'est utilise que pour les VM ; un stockage peut passer None.
    """
    rows = list(
        db.scalars(
            select(ResourceShare).where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == resource_id,
                ResourceShare.status == ShareStatus.ACTIVE.value,
            )
        )
    )
    for row in rows:
        if row.resource_type == ResourceType.VM.value:
            if network is None:
                raise RuntimeError("Le detachement reseau d'une VM exige le port Reseau.")
            try:
                await network.detach_vm_from_project(VmRef(row.resource_id), row.dest_project_id)
            except NetworkUnavailable:
                raise upstream_unavailable("Reseau") from None
            _drop_dest_links(db, row.resource_id, row.dest_project_id)
        row.status = ShareStatus.REVOKED.value
        record_audit(
            db,
            actor_id=actor_id,
            action="share.revoked",
            entity_type="share",
            entity_id=row.id,
            data={"reason": "resource_deleted"},
        )
    return rows


async def revoke_received_by_project(
    db: Session,
    network: NetworkPort,
    *,
    actor_id: str,
    project_id: str,
) -> None:
    """Revoque les partages recus par un projet sans supprimer les ressources. Ne commit pas."""
    rows = list(
        db.scalars(
            select(ResourceShare).where(
                ResourceShare.dest_project_id == project_id,
                ResourceShare.status == ShareStatus.ACTIVE.value,
            )
        )
    )
    for row in rows:
        if row.resource_type == ResourceType.VM.value:
            try:
                await network.detach_vm_from_project(VmRef(row.resource_id), project_id)
            except NetworkUnavailable:
                raise upstream_unavailable("Reseau") from None
            _drop_dest_links(db, row.resource_id, project_id)
        row.status = ShareStatus.REVOKED.value
        record_audit(
            db,
            actor_id=actor_id,
            action="share.revoked",
            entity_type="share",
            entity_id=row.id,
            data={"reason": "dest_project_deleted"},
        )


async def revoke_share(
    db: Session,
    network: NetworkPort,
    iam: IamPort,
    *,
    user_id: str,
    share_id: str,
) -> ResourceShare:
    """Retire un partage actif. Une VM quitte les reseaux du projet destinataire (R21).

    Le proprietaire de l'origine peut toujours revoquer. L'auteur du partage doit
    encore etre membre d'au moins un des deux projets concernes.
    """
    row = db.get(ResourceShare, share_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Partage introuvable.")
    origin = _project(db, row.origin_project_id)
    if user_id != origin.owner_id:
        if user_id != row.created_by:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Seul le proprietaire du projet d'origine ou l'auteur du partage peut le revoquer.",
            )
        origin_member = await _member(iam, user_id, row.origin_project_id)
        dest_member = await _member(iam, user_id, row.dest_project_id)
        if not (origin_member or dest_member):
            raise AppError(
                ErrorCode.FORBIDDEN,
                "L'utilisateur n'est membre d'aucun des projets concernes par le partage.",
            )
    if row.status != ShareStatus.ACTIVE.value:
        raise AppError(ErrorCode.INVALID_STATE, "Ce partage est deja revoque.")
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
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return row


async def get_share(db: Session, iam: IamPort, *, user_id: str, share_id: str) -> ResourceShare:
    """Retourne un partage si l'appelant est membre d'un projet concerne et y a le `.view`."""
    row = db.get(ResourceShare, share_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Partage introuvable.")
    projects = await iam.list_projects(user_id)
    if row.origin_project_id not in projects and row.dest_project_id not in projects:
        raise AppError(ErrorCode.FORBIDDEN, "Ce partage ne vous est pas accessible.")
    view_right = _VIEW_RIGHT[ResourceType(row.resource_type)]
    allowed = False
    for project_id in (row.origin_project_id, row.dest_project_id):
        if project_id in projects:
            rights = await iam.get_rights(user_id, project_id)
            if view_right in rights:
                allowed = True
                break
    if not allowed:
        raise AppError(ErrorCode.FORBIDDEN, f"Droit requis manquant : {view_right}.")
    return row


async def list_shares(
    db: Session,
    iam: IamPort,
    *,
    user_id: str,
    params: PageParams,
) -> tuple[list[ResourceShare], int]:
    """Liste paginee des partages visibles via un droit `.view` (sans bypass admin)."""
    projects = await iam.list_projects(user_id)
    if not projects:
        return [], 0
    conditions = []
    for project_id in projects:
        rights = await iam.get_rights(user_id, project_id)
        for resource_type, view_right in _VIEW_RIGHT.items():
            if view_right not in rights:
                continue
            conditions.append(
                and_(
                    ResourceShare.origin_project_id == project_id,
                    ResourceShare.resource_type == resource_type.value,
                )
            )
            conditions.append(
                and_(
                    ResourceShare.dest_project_id == project_id,
                    ResourceShare.resource_type == resource_type.value,
                )
            )
    if not conditions:
        return [], 0
    statement = (
        select(ResourceShare)
        .where(or_(*conditions))
        .order_by(ResourceShare.created_at.desc())
    )
    rows, total = paginate(db, statement, params)
    return list(rows), total
