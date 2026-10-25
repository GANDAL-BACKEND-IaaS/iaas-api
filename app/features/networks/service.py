"""Services reseau.

Action directe, sans demande. Seules les VMs visibles dans le projet peuvent etre reliees.
Lecture : proprietaire ou `vm.view`. Ecriture : proprietaire ou `vm.network`.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.application.ports.hypervisor import VmRef
from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort, NetworkRef, NetworkUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import Page, PageParams, paginate
from app.features.networks.schemas import NetworkOut
from app.features.shares.service import visible_in_project
from app.shared.deletion import DeletionOut, DeletionPreviewOut, expected_text, is_confirmed
from app.shared.enums import ResourceType, VmState
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.projects import Project
from app.shared.models.storages import Storage
from app.shared.models.vms import Vm
from app.shared.policies.access import authorize


def _project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


def _network(db: Session, project_id: str, network_id: str) -> Network:
    row = db.get(Network, network_id)
    if row is None or row.project_id != project_id:
        raise AppError(ErrorCode.NOT_FOUND, "Reseau introuvable.")
    return row


def _out(db: Session, row: Network) -> NetworkOut:
    vm_ids = list(db.scalars(select(NetworkVm.vm_id).where(NetworkVm.network_id == row.id)))
    return NetworkOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        vm_ids=sorted(vm_ids),
        created_at=row.created_at,
    )


async def _authorize_read(iam: IamPort, user_id: str, project_id: str) -> None:
    """Lecture autorisee par `vm.view` (le proprietaire a tous les droits)."""
    if project_id not in await iam.list_projects(user_id):
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur n'est pas membre du projet.")
    rights = await iam.get_rights(user_id, project_id)
    if "vm.view" not in rights:
        raise AppError(ErrorCode.FORBIDDEN, "Droit requis manquant : vm.view.")


def _same_name(db: Session, project_id: str, name: str, exclude_id: str | None = None) -> bool:
    statement = select(Network.id).where(Network.project_id == project_id, Network.name == name)
    if exclude_id is not None:
        statement = statement.where(Network.id != exclude_id)
    return db.scalar(statement) is not None


async def create_network(
    db: Session,
    iam: IamPort,
    port: NetworkPort,
    identity: Identity,
    project_id: str,
    name: str,
) -> NetworkOut:
    """F7 : cree un reseau dans le projet."""
    _project(db, project_id)
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    if _same_name(db, project_id, name):
        raise AppError(ErrorCode.CONFLICT, "Ce nom de reseau est deja utilise dans le projet.")
    try:
        ref = await port.create_network(project_id, name)
    except NetworkUnavailable:
        raise upstream_unavailable("Reseau") from None
    row = Network(id=ref.network_id, project_id=project_id, name=name)
    db.add(row)
    record_audit(
        db, actor_id=identity.user_id, action="network.created", entity_type="network", entity_id=row.id
    )
    db.commit()
    db.refresh(row)
    return _out(db, row)


async def list_networks(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    params: PageParams,
    *,
    name: str | None = None,
) -> Page[NetworkOut]:
    """F7 : liste paginee des reseaux du projet, triee par nom puis identifiant."""
    _project(db, project_id)
    await _authorize_read(iam, identity.user_id, project_id)
    statement = select(Network).where(Network.project_id == project_id)
    if name:
        statement = statement.where(Network.name.ilike(f"{name}%"))
    rows, total = paginate(db, statement.order_by(Network.name, Network.id), params)
    return Page.build([_out(db, row) for row in rows], total, params)


async def get_network(
    db: Session, iam: IamPort, identity: Identity, project_id: str, network_id: str
) -> NetworkOut:
    """F7 : lit un reseau du projet."""
    _project(db, project_id)
    row = _network(db, project_id, network_id)
    await _authorize_read(iam, identity.user_id, project_id)
    return _out(db, row)


async def update_network(
    db: Session,
    iam: IamPort,
    port: NetworkPort,
    identity: Identity,
    project_id: str,
    network_id: str,
    name: str,
) -> NetworkOut:
    """F7 : renomme un reseau. L'appel externe precede la modification locale."""
    _project(db, project_id)
    row = _network(db, project_id, network_id)
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    if _same_name(db, project_id, name, exclude_id=row.id):
        raise AppError(ErrorCode.CONFLICT, "Ce nom de reseau est deja utilise dans le projet.")
    try:
        await port.rename_network(NetworkRef(row.id), name)
    except NetworkUnavailable:
        db.rollback()
        raise upstream_unavailable("Reseau") from None
    row.name = name
    record_audit(
        db,
        actor_id=identity.user_id,
        action="network.renamed",
        entity_type="network",
        entity_id=row.id,
        data={"name": name},
    )
    db.commit()
    db.refresh(row)
    return _out(db, row)


async def attach_vm(
    db: Session,
    iam: IamPort,
    port: NetworkPort,
    identity: Identity,
    project_id: str,
    network_id: str,
    vm_id: str,
) -> NetworkOut:
    """F7 : rattache une VM visible dans le projet. Ajout idempotent."""
    _project(db, project_id)
    row = _network(db, project_id, network_id)
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    if db.get(Storage, vm_id) is not None:
        raise AppError(ErrorCode.BAD_REQUEST, "Cet identifiant designe un stockage, pas une VM.")
    vm = db.get(Vm, vm_id)
    if vm is None or not visible_in_project(
        db,
        resource_type=ResourceType.VM.value,
        resource_id=vm.id,
        origin_project_id=vm.origin_project_id,
        project_id=project_id,
    ):
        raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")
    if vm.state == VmState.DELETING.value:
        raise AppError(ErrorCode.INVALID_STATE, "La VM est en cours de suppression.")
    if db.get(NetworkVm, (network_id, vm_id)) is not None:
        return _out(db, row)
    try:
        await port.attach_vm(NetworkRef(row.id), VmRef(vm_id))
    except NetworkUnavailable:
        db.rollback()
        raise upstream_unavailable("Reseau") from None
    db.add(NetworkVm(network_id=row.id, vm_id=vm_id))
    record_audit(
        db,
        actor_id=identity.user_id,
        action="network.vm_attached",
        entity_type="network",
        entity_id=row.id,
        data={"vm_id": vm_id},
    )
    db.commit()
    db.refresh(row)
    return _out(db, row)


async def detach_vm(
    db: Session,
    iam: IamPort,
    port: NetworkPort,
    identity: Identity,
    project_id: str,
    network_id: str,
    vm_id: str,
) -> NetworkOut:
    """F7 : retire une VM du reseau. Retrait idempotent."""
    _project(db, project_id)
    row = _network(db, project_id, network_id)
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    link = db.get(NetworkVm, (network_id, vm_id))
    if link is None:
        return _out(db, row)
    try:
        await port.detach_vm(NetworkRef(row.id), VmRef(vm_id))
    except NetworkUnavailable:
        db.rollback()
        raise upstream_unavailable("Reseau") from None
    db.delete(link)
    record_audit(
        db,
        actor_id=identity.user_id,
        action="network.vm_detached",
        entity_type="network",
        entity_id=row.id,
        data={"vm_id": vm_id},
    )
    db.commit()
    db.refresh(row)
    return _out(db, row)


async def delete_network(
    db: Session,
    iam: IamPort,
    port: NetworkPort,
    identity: Identity,
    project_id: str,
    network_id: str,
    confirmation_text: str | None,
) -> DeletionPreviewOut | DeletionOut:
    """F7 : protocole de suppression en deux temps. Aucun effet local si le port echoue."""
    _project(db, project_id)
    row = _network(db, project_id, network_id)
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    text = expected_text(row.name)
    if not is_confirmed(confirmation_text, text):
        count = len(list(db.scalars(select(NetworkVm.vm_id).where(NetworkVm.network_id == row.id))))
        return DeletionPreviewOut(
            confirmation_text=text,
            warning=(
                f"Le reseau {row.name} sera supprime et {count} VM seront deconnectees. "
                "Cette action est irreversible."
            ),
        )
    try:
        await port.delete_network(NetworkRef(row.id))
    except NetworkUnavailable:
        db.rollback()
        raise upstream_unavailable("Reseau") from None
    record_audit(
        db, actor_id=identity.user_id, action="network.deleted", entity_type="network", entity_id=row.id
    )
    db.execute(delete(NetworkVm).where(NetworkVm.network_id == row.id))
    db.delete(row)
    db.commit()
    return DeletionOut(
        resource_type="network",
        resource_id=network_id,
        message=f"Le reseau {row.name} a bien ete supprime.",
    )
