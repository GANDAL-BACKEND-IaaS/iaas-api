"""Services VM.

Les creations et modifications passent par le moteur de demandes.
Les actions directes appellent les ports et ne sont jamais appliquees a moitie.
"""

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.application.ports.dns import DnsPort, DnsUnavailable
from app.application.ports.hypervisor import HypervisorPort, HypervisorUnavailable, VmRef
from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort, NetworkUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import Page, PageParams, paginate
from app.features.requests.schemas import RequestOut, VMCreateRequestIn, VMUpdateRequestIn
from app.features.requests.service import submit_request
from app.features.shares.service import revoke_all_for_resource, visible_in_project
from app.features.vms.schemas import ConsoleOut, PowerOut, VMOut
from app.shared.deletion import (
    DeletionOut,
    DeletionPreviewOut,
    expected_text,
    is_confirmed,
)
from app.shared.enums import (
    POWER_ALLOWED,
    POWER_TARGET,
    PowerAction,
    RequestKind,
    ResourceType,
    VmState,
)
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.projects import Project
from app.shared.models.shares import ResourceShare
from app.shared.models.vms import Vm
from app.shared.policies.access import ResourceView, authorize


def _out(vm: Vm, project_id: str) -> VMOut:
    """Projette une VM en ajoutant le drapeau shared pour le projet consulte."""
    item = VMOut.model_validate(vm)
    return item.model_copy(update={"shared": vm.origin_project_id != project_id})


def _project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


def _load(db: Session, vm_id: str) -> Vm:
    vm = db.get(Vm, vm_id)
    if vm is None:
        raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")
    return vm


def _visible_or_404(db: Session, vm: Vm, project_id: str) -> None:
    if not visible_in_project(
        db,
        resource_type=ResourceType.VM.value,
        resource_id=vm.id,
        origin_project_id=vm.origin_project_id,
        project_id=project_id,
    ):
        raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")


async def request_create_vm(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    body: VMCreateRequestIn,
) -> RequestOut:
    """F1 : depose une demande de creation. La VM n'existe qu'apres acceptation."""
    row = await submit_request(
        db,
        iam,
        author_id=identity.user_id,
        project_id=project_id,
        kind=RequestKind.VM_CREATE,
        payload=body.model_dump(),
        target_resource_id=None,
    )
    return RequestOut.model_validate(row)


async def request_update_vm(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
    body: VMUpdateRequestIn,
) -> RequestOut:
    """F2 : depose une demande de modification de la configuration complete."""
    row = await submit_request(
        db,
        iam,
        author_id=identity.user_id,
        project_id=project_id,
        kind=RequestKind.VM_UPDATE,
        payload=body.model_dump(),
        target_resource_id=vm_id,
    )
    return RequestOut.model_validate(row)


async def list_vms(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    params: PageParams,
    *,
    state: VmState | None = None,
    shared: bool | None = None,
    ip_address: str | None = None,
    name: str | None = None,
) -> Page[VMOut]:
    """F3 : liste les VMs du projet, y compris celles qui y sont partagees."""
    _project(db, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="vm.view",
    )
    shared_ids = select(ResourceShare.resource_id).where(
        ResourceShare.resource_type == ResourceType.VM.value,
        ResourceShare.dest_project_id == project_id,
        ResourceShare.status == "active",
    )
    if shared is True:
        statement = select(Vm).where(Vm.id.in_(shared_ids))
    elif shared is False:
        statement = select(Vm).where(Vm.origin_project_id == project_id)
    else:
        statement = select(Vm).where(
            or_(Vm.origin_project_id == project_id, Vm.id.in_(shared_ids))
        )
    if state is not None:
        statement = statement.where(Vm.state == state.value)
    if ip_address is not None:
        statement = statement.where(Vm.ip_address == ip_address)
    if name:
        statement = statement.where(Vm.name.ilike(f"{name}%"))
    rows, total = paginate(db, statement.order_by(Vm.name, Vm.id), params)
    return Page.build([_out(vm, project_id) for vm in rows], total, params)


async def get_vm(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
) -> VMOut:
    """F3 : consulte une VM visible dans le projet."""
    _project(db, project_id)
    vm = _load(db, vm_id)
    _visible_or_404(db, vm, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="vm.view",
        resource=ResourceView(ResourceType.VM.value, vm.id, vm.origin_project_id),
    )
    return _out(vm, project_id)


async def power_vm(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
    action: PowerAction,
) -> PowerOut:
    """F4 : demarre, arrete ou redemarre une VM, sans demande."""
    _project(db, project_id)
    vm = _load(db, vm_id)
    _visible_or_404(db, vm, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="vm.power",
        resource=ResourceView(ResourceType.VM.value, vm.id, vm.origin_project_id),
    )
    if VmState(vm.state) not in POWER_ALLOWED[action]:
        raise AppError(ErrorCode.INVALID_STATE, "Action incompatible avec l'etat de la VM.")
    target, transient = POWER_TARGET[action]
    try:
        await hypervisor.power(VmRef(vm.id), action)
    except (HypervisorUnavailable, KeyError):
        db.rollback()
        raise upstream_unavailable("Hyperviseur") from None
    vm.state = target.value
    record_audit(
        db,
        actor_id=identity.user_id,
        action="vm.power",
        entity_type="vm",
        entity_id=vm.id,
        data={"power": action.value},
    )
    db.commit()
    db.refresh(vm)
    return PowerOut(vm_id=vm.id, action=action, state=transient)


async def console_vm(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
) -> ConsoleOut:
    """F5 : verifie le droit et le partage actif, puis fournit l'acces console."""
    _project(db, project_id)
    vm = _load(db, vm_id)
    _visible_or_404(db, vm, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="vm.console",
        resource=ResourceView(ResourceType.VM.value, vm.id, vm.origin_project_id),
    )
    try:
        access = await hypervisor.console(VmRef(vm.id))
    except (HypervisorUnavailable, KeyError):
        raise upstream_unavailable("Hyperviseur") from None
    return ConsoleOut(url=access.url, expires_in=access.expires_in)


def _network_projects(db: Session, vm_id: str) -> list[str]:
    statement = (
        select(Network.project_id)
        .join(NetworkVm, NetworkVm.network_id == Network.id)
        .where(NetworkVm.vm_id == vm_id)
        .distinct()
    )
    return list(db.scalars(statement))


async def delete_vm_infrastructure(
    db: Session,
    hypervisor: HypervisorPort,
    network: NetworkPort,
    dns: DnsPort,
    *,
    actor_id: str,
    vm: Vm,
) -> None:
    """Effets externes et suppression locale d'une VM. N'enregistre pas la transaction."""
    projects = set(_network_projects(db, vm.id))
    await revoke_all_for_resource(
        db,
        network,
        actor_id=actor_id,
        resource_type=ResourceType.VM.value,
        resource_id=vm.id,
    )
    for owner in projects:
        await network.detach_vm_from_project(VmRef(vm.id), owner)
    await dns.delete_domain(vm.id)
    await hypervisor.delete_vm(VmRef(vm.id))
    db.execute(delete(NetworkVm).where(NetworkVm.vm_id == vm.id))
    record_audit(
        db,
        actor_id=actor_id,
        action="vm.deleted",
        entity_type="vm",
        entity_id=vm.id,
    )
    db.delete(vm)


async def delete_vm(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    network: NetworkPort,
    dns: DnsPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
    confirmation_text: str | None,
) -> DeletionPreviewOut | DeletionOut:
    """F6 : protocole de suppression en deux temps, avec effets orchestres."""
    _project(db, project_id)
    vm = _load(db, vm_id)
    _visible_or_404(db, vm, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="vm.delete",
        resource=ResourceView(ResourceType.VM.value, vm.id, vm.origin_project_id),
    )
    text = expected_text(vm.name)
    if not is_confirmed(confirmation_text, text):
        shares = db.scalar(
            select(ResourceShare).where(
                ResourceShare.resource_type == ResourceType.VM.value,
                ResourceShare.resource_id == vm.id,
                ResourceShare.status == "active",
            ).limit(1)
        )
        networks = len(_network_projects(db, vm.id))
        warning = (
            f"La VM {vm.name} sera supprimee, retiree de {networks} reseau(x) et "
            f"{'ses partages actifs seront revoques' if shares is not None else 'aucun partage actif a revoquer'}. "
            "Cette action est irreversible."
        )
        return DeletionPreviewOut(confirmation_text=text, warning=warning)
    try:
        await delete_vm_infrastructure(
            db,
            hypervisor,
            network,
            dns,
            actor_id=identity.user_id,
            vm=vm,
        )
    except AppError:
        db.rollback()
        raise
    except (NetworkUnavailable, DnsUnavailable, HypervisorUnavailable, KeyError):
        db.rollback()
        raise upstream_unavailable("infrastructure") from None
    db.commit()
    return DeletionOut(
        resource_type="vm",
        resource_id=vm_id,
        message=f"La VM {vm.name} a bien ete supprimee.",
    )
