"""Services VM. Proprietaire : NAOMI (port VM).

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
from app.features.requests.schemas import RequestOut
from app.features.requests.service import submit_request
from app.features.shares.schemas import ShareOut
from app.features.shares.service import create_share, revoke_all_for_resource, visible_in_project
from app.features.vms.schemas import (
    ConsoleOut,
    VmOut,
    VmRequestCreateIn,
    VmRequestUpdateIn,
)
from app.shared.enums import PowerAction, RequestKind, ResourceType, VmState
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.shares import ResourceShare
from app.shared.models.vms import Vm
from app.shared.policies.access import ResourceView, authorize


def _out(vm: Vm, project_id: str) -> VmOut:
    """Projette une VM en ajoutant le drapeau shared pour le projet consulte."""
    item = VmOut.model_validate(vm)
    return item.model_copy(update={"shared": vm.origin_project_id != project_id})


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
    body: VmRequestCreateIn,
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
    body: VmRequestUpdateIn,
) -> RequestOut:
    """F2 : depose une demande de modification des caracteristiques de base."""
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
) -> Page[VmOut]:
    """F3 : liste les VMs du projet, y compris celles qui y sont partagees."""
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
    statement = (
        select(Vm)
        .where(or_(Vm.origin_project_id == project_id, Vm.id.in_(shared_ids)))
        .order_by(Vm.created_at.desc())
    )
    rows, total = paginate(db, statement, params)
    return Page[VmOut](
        items=[_out(vm, project_id) for vm in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def get_vm(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
) -> VmOut:
    """F3 : consulte une VM visible dans le projet."""
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


def _next_state(vm: Vm, action: PowerAction) -> str:
    if action == PowerAction.START and vm.state == VmState.STOPPED.value:
        return VmState.RUNNING.value
    if action == PowerAction.STOP and vm.state == VmState.RUNNING.value:
        return VmState.STOPPED.value
    if action == PowerAction.RESTART and vm.state == VmState.RUNNING.value:
        return VmState.RUNNING.value
    raise AppError(ErrorCode.INVALID_STATE, "Action incompatible avec l'etat de la VM.")


async def power_vm(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
    action: PowerAction,
) -> VmOut:
    """F4 : demarre, arrete ou redemarre une VM, sans demande."""
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
    new_state = _next_state(vm, action)
    try:
        await hypervisor.power(VmRef(vm.id), action)
    except (HypervisorUnavailable, KeyError):
        db.rollback()
        raise upstream_unavailable("Hyperviseur") from None
    vm.state = new_state
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
    return _out(vm, project_id)


async def console_vm(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
) -> ConsoleOut:
    """F5 : verifie le droit et le partage actif, puis fournit l'acces console."""
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
    except HypervisorUnavailable:
        raise upstream_unavailable("Hyperviseur") from None
    except KeyError:
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


async def delete_vm(
    db: Session,
    iam: IamPort,
    hypervisor: HypervisorPort,
    network: NetworkPort,
    dns: DnsPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
    confirm: bool,
) -> None:
    """F6 : supprime la VM apres confirmation, revoque les partages et appelle le DNS."""
    if confirm is not True:
        raise AppError(ErrorCode.VALIDATION_ERROR, "La suppression exige une confirmation explicite.")
    vm = _load(db, vm_id)
    if vm.state == VmState.DELETING.value:
        raise AppError(ErrorCode.INVALID_STATE, "La VM est deja en cours de suppression.")
    _visible_or_404(db, vm, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="vm.delete",
        resource=ResourceView(ResourceType.VM.value, vm.id, vm.origin_project_id),
    )
    projects = set(_network_projects(db, vm.id))
    try:
        await revoke_all_for_resource(
            db,
            network,
            actor_id=identity.user_id,
            resource_type=ResourceType.VM.value,
            resource_id=vm.id,
        )
        for owner in projects:
            await network.detach_vm_from_project(VmRef(vm.id), owner)
        await dns.delete_domain(vm.id)
        await hypervisor.delete_vm(VmRef(vm.id))
    except (NetworkUnavailable, DnsUnavailable, HypervisorUnavailable):
        db.rollback()
        raise upstream_unavailable("infrastructure") from None
    except AppError:
        db.rollback()
        raise
    db.execute(delete(NetworkVm).where(NetworkVm.vm_id == vm.id))
    record_audit(
        db,
        actor_id=identity.user_id,
        action="vm.deleted",
        entity_type="vm",
        entity_id=vm.id,
    )
    db.delete(vm)
    db.commit()


async def share_vm(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    vm_id: str,
    dest_project_id: str,
) -> ShareOut:
    """F14 : partage la VM depuis son projet d'origine."""
    vm = _load(db, vm_id)
    if vm.origin_project_id != project_id:
        raise AppError(ErrorCode.FORBIDDEN, "Le partage se fait depuis le projet d'origine.")
    row = await create_share(
        db,
        iam,
        user_id=identity.user_id,
        resource_type=ResourceType.VM,
        resource_id=vm_id,
        dest_project_id=dest_project_id,
    )
    return ShareOut.model_validate(row)
