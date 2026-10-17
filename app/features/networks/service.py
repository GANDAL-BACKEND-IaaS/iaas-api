"""Services reseau. Proprietaire : KOM (port Reseau).

Action directe, sans demande. Seules les VMs visibles dans le projet peuvent etre reliees.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.hypervisor import VmRef
from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort, NetworkRef, NetworkUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import Page, PageParams, paginate
from app.features.networks.schemas import NetworkOut
from app.features.shares.service import visible_in_project
from app.shared.enums import ResourceType
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.vms import Vm
from app.shared.policies.access import authorize


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


async def create_network(
    db: Session,
    iam: IamPort,
    port: NetworkPort,
    identity: Identity,
    project_id: str,
    name: str,
) -> NetworkOut:
    """F7 : cree un reseau dans le projet."""
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
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
    db: Session, iam: IamPort, identity: Identity, project_id: str, params: PageParams
) -> Page[NetworkOut]:
    """F7 : liste paginee des reseaux du projet."""
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    statement = select(Network).where(Network.project_id == project_id).order_by(Network.created_at.desc())
    rows, total = paginate(db, statement, params)
    return Page[NetworkOut](
        items=[_out(db, row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def attach_vm(
    db: Session,
    iam: IamPort,
    port: NetworkPort,
    identity: Identity,
    project_id: str,
    network_id: str,
    vm_id: str,
) -> NetworkOut:
    """F7 : rattache une VM visible dans le projet."""
    row = _network(db, project_id, network_id)
    vm = db.get(Vm, vm_id)
    if vm is None or not visible_in_project(
        db,
        resource_type=ResourceType.VM.value,
        resource_id=vm.id,
        origin_project_id=vm.origin_project_id,
        project_id=project_id,
    ):
        raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    if db.get(NetworkVm, (network_id, vm_id)) is not None:
        raise AppError(ErrorCode.CONFLICT, "La VM est deja rattachee a ce reseau.")
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
    """F7 : retire une VM du reseau."""
    row = _network(db, project_id, network_id)
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    link = db.get(NetworkVm, (network_id, vm_id))
    if link is None:
        raise AppError(ErrorCode.NOT_FOUND, "La VM n'est pas rattachee a ce reseau.")
    try:
        await port.detach_vm(NetworkRef(row.id), VmRef(vm_id))
    except NetworkUnavailable:
        db.rollback()
        raise upstream_unavailable("Reseau") from None
    db.delete(link)
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
) -> None:
    """F7 : supprime le reseau."""
    row = _network(db, project_id, network_id)
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="vm.network"
    )
    try:
        await port.delete_network(NetworkRef(row.id))
    except NetworkUnavailable:
        raise upstream_unavailable("Reseau") from None
    record_audit(
        db, actor_id=identity.user_id, action="network.deleted", entity_type="network", entity_id=row.id
    )
    db.delete(row)
    db.commit()
