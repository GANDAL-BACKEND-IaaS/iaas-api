"""Services metier du domaine Reseau. Proprietaire : KOM (port Reseau).

Les reseaux permettent de regrouper des VMs visibles au sein d'un projet donne (F7, R21).
Aucun espace de stockage n'est jamais mis en reseau (R22).
Les actions sont directes (sans demande d'approbation administrateur).
"""

import re
import unicodedata

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.application.ports.hypervisor import VmRef
from app.application.ports.iam import IamPort
from app.application.ports.network import (
    NetworkError,
    NetworkPort,
    NetworkRef,
    NetworkUnavailable,
)
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import PageParams, paginate
from app.shared.enums import ResourceType, VmState
from app.shared.models.networks import Network, NetworkVm
from app.shared.models.projects import Project
from app.shared.models.storages import Storage
from app.shared.models.vms import Vm
from app.shared.policies.access import authorize
from app.shared.policies.visibility import is_resource_visible


def slugify(value: str) -> str:
    """Convertit une chaine en slug ASCII (minuscules, tirets, sans accents)."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s-]", "", normalized).strip().lower()
    return re.sub(r"[-\s]+", "-", cleaned)


def _ensure_slug_unique(db: Session, name: str, exclude_network_id: str | None = None) -> None:
    """Garantit qu'aucun autre reseau du systeme ne possede le meme nom ou slug."""
    target_slug = slugify(name)
    existing_networks = db.scalars(select(Network)).all()
    for net in existing_networks:
        if exclude_network_id is not None and net.id == exclude_network_id:
            continue
        if slugify(net.name) == target_slug:
            raise AppError(
                ErrorCode.CONFLICT,
                f"Un reseau avec le nom ou slug '{net.name}' existe deja dans le systeme.",
            )


def _get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


def _get_network_in_project(db: Session, project_id: str, network_id: str) -> Network:
    network = db.get(Network, network_id)
    if network is None or network.project_id != project_id:
        raise AppError(ErrorCode.NOT_FOUND, "Reseau introuvable dans ce projet.")
    return network


async def _authorize_view_network(iam: IamPort, user_id: str, project_id: str) -> None:
    """Verifie que l'utilisateur est membre et dispose de vm.view ou vm.network (ou proprietaire)."""
    projects = await iam.list_projects(user_id)
    if project_id not in projects:
        raise AppError(ErrorCode.FORBIDDEN, "L'utilisateur n'est pas membre du projet.")
    rights = await iam.get_rights(user_id, project_id)
    if "vm.view" not in rights and "vm.network" not in rights:
        raise AppError(ErrorCode.FORBIDDEN, "Droit requis manquant : vm.view ou vm.network.")


async def create_network(
    db: Session,
    iam: IamPort,
    network_port: NetworkPort,
    *,
    actor_id: str,
    project_id: str,
    name: str,
) -> Network:
    """F7 : cree un reseau dans un projet. Action directe, sans demande."""
    _get_project(db, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=actor_id,
        project_id=project_id,
        required_right="vm.network",
    )
    _ensure_slug_unique(db, name)

    try:
        ref = await network_port.create_network(project_id, name)
    except NetworkUnavailable:
        raise upstream_unavailable("Reseau") from None
    except NetworkError as err:
        raise AppError(ErrorCode.UPSTREAM_UNAVAILABLE, str(err)) from None

    network = Network(id=ref.network_id, project_id=project_id, name=name)
    db.add(network)
    db.flush()
    record_audit(
        db,
        actor_id=actor_id,
        action="network.created",
        entity_type="network",
        entity_id=network.id,
        data={"name": name, "project_id": project_id},
    )
    db.commit()
    db.refresh(network)
    return network


async def list_networks(
    db: Session,
    iam: IamPort,
    *,
    actor_id: str,
    project_id: str,
    params: PageParams,
) -> tuple[list[Network], int]:
    """F7 : liste paginee des reseaux du projet."""
    _get_project(db, project_id)
    await _authorize_view_network(iam, actor_id, project_id)

    statement = (
        select(Network)
        .where(Network.project_id == project_id)
        .order_by(Network.created_at.desc())
    )
    rows, total = paginate(db, statement, params)
    return list(rows), total


async def get_network(
    db: Session,
    iam: IamPort,
    *,
    actor_id: str,
    project_id: str,
    network_id: str,
) -> Network:
    """Consulte un reseau unitaire dans le projet."""
    _get_project(db, project_id)
    await _authorize_view_network(iam, actor_id, project_id)
    return _get_network_in_project(db, project_id, network_id)


async def rename_network(
    db: Session,
    iam: IamPort,
    *,
    actor_id: str,
    project_id: str,
    network_id: str,
    new_name: str,
) -> Network:
    """Modifie le nom d'un reseau au sein du projet."""
    _get_project(db, project_id)
    network = _get_network_in_project(db, project_id, network_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=actor_id,
        project_id=project_id,
        required_right="vm.network",
    )
    _ensure_slug_unique(db, new_name, exclude_network_id=network.id)

    old_name = network.name
    network.name = new_name
    record_audit(
        db,
        actor_id=actor_id,
        action="network.renamed",
        entity_type="network",
        entity_id=network.id,
        data={"old_name": old_name, "new_name": new_name, "project_id": project_id},
    )
    db.commit()
    db.refresh(network)
    return network


async def attach_vm(
    db: Session,
    iam: IamPort,
    network_port: NetworkPort,
    *,
    actor_id: str,
    project_id: str,
    network_id: str,
    vm_id: str,
) -> Network:
    """F7 : rattache une VM visible dans le projet au reseau (R21). Refuse tout stockage (R22)."""
    _get_project(db, project_id)
    network = _get_network_in_project(db, project_id, network_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=actor_id,
        project_id=project_id,
        required_right="vm.network",
    )

    # R22 : un stockage n'est jamais mis en reseau
    if db.get(Storage, vm_id) is not None:
        raise AppError(ErrorCode.BAD_REQUEST, "Un espace de stockage ne peut pas etre mis en reseau (R22).")

    vm = db.get(Vm, vm_id)
    if vm is None:
        raise AppError(ErrorCode.NOT_FOUND, "Machine virtuelle introuvable.")

    if vm.state == VmState.DELETING.value:
        raise AppError(ErrorCode.INVALID_STATE, "La VM est en cours de suppression.")

    # Visibilite : VM d'origine ou partage actif vers ce projet
    if not is_resource_visible(
        db,
        resource_type=ResourceType.VM.value,
        resource_id=vm.id,
        origin_project_id=vm.origin_project_id,
        project_id=project_id,
    ):
        raise AppError(ErrorCode.FORBIDDEN, "La VM n'est pas visible dans ce projet.")

    # Idempotence : si deja rattaché en base, on retourne directement
    existing_link = db.get(NetworkVm, (network.id, vm.id))
    if existing_link is not None:
        return network

    try:
        await network_port.attach_vm(NetworkRef(network.id), VmRef(vm.id))
    except NetworkUnavailable:
        raise upstream_unavailable("Reseau") from None
    except NetworkError as err:
        raise AppError(ErrorCode.UPSTREAM_UNAVAILABLE, str(err)) from None

    link = NetworkVm(network_id=network.id, vm_id=vm.id)
    db.add(link)
    record_audit(
        db,
        actor_id=actor_id,
        action="network.vm_attached",
        entity_type="network",
        entity_id=network.id,
        data={"vm_id": vm.id, "project_id": project_id},
    )
    db.commit()
    db.refresh(network)
    return network


async def detach_vm(
    db: Session,
    iam: IamPort,
    network_port: NetworkPort,
    *,
    actor_id: str,
    project_id: str,
    network_id: str,
    vm_id: str,
) -> Network:
    """F7 : retire une VM du reseau. Idempotent si la VM n'y est pas."""
    _get_project(db, project_id)
    network = _get_network_in_project(db, project_id, network_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=actor_id,
        project_id=project_id,
        required_right="vm.network",
    )

    link = db.get(NetworkVm, (network.id, vm_id))
    if link is None:
        return network

    try:
        await network_port.detach_vm(NetworkRef(network.id), VmRef(vm_id))
    except NetworkUnavailable:
        raise upstream_unavailable("Reseau") from None
    except NetworkError as err:
        raise AppError(ErrorCode.UPSTREAM_UNAVAILABLE, str(err)) from None

    db.delete(link)
    record_audit(
        db,
        actor_id=actor_id,
        action="network.vm_detached",
        entity_type="network",
        entity_id=network.id,
        data={"vm_id": vm_id, "project_id": project_id},
    )
    db.commit()
    db.refresh(network)
    return network


async def delete_network(
    db: Session,
    iam: IamPort,
    network_port: NetworkPort,
    *,
    actor_id: str,
    project_id: str,
    network_id: str,
) -> None:
    """F7 : supprime un reseau du projet."""
    _get_project(db, project_id)
    network = _get_network_in_project(db, project_id, network_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=actor_id,
        project_id=project_id,
        required_right="vm.network",
    )

    try:
        await network_port.delete_network(NetworkRef(network.id))
    except NetworkUnavailable:
        raise upstream_unavailable("Reseau") from None
    except NetworkError as err:
        raise AppError(ErrorCode.UPSTREAM_UNAVAILABLE, str(err)) from None

    record_audit(
        db,
        actor_id=actor_id,
        action="network.deleted",
        entity_type="network",
        entity_id=network.id,
        data={"name": network.name, "project_id": project_id},
    )
    db.delete(network)
    db.commit()


# =====================================================================
# FONCTIONS D'INTEGRATION INTERNES (POUR LES AUTRES EQUIPES)
# =====================================================================

async def detach_vm_from_all_networks(
    db: Session,
    network_port: NetworkPort,
    *,
    vm_id: str,
) -> None:
    """Appele lors de la suppression d'une VM (NAOMI - F6, R21). Idempotent."""
    links = db.scalars(select(NetworkVm).where(NetworkVm.vm_id == vm_id)).all()
    for link in links:
        try:
            await network_port.detach_vm(NetworkRef(link.network_id), VmRef(vm_id))
        except NetworkUnavailable:
            raise upstream_unavailable("Reseau") from None
        except NetworkError:
            pass
    db.execute(delete(NetworkVm).where(NetworkVm.vm_id == vm_id))
    db.commit()


async def detach_vm_from_project_networks(
    db: Session,
    network_port: NetworkPort,
    *,
    vm_id: str,
    project_id: str,
) -> None:
    """Appele lors du retrait d'un partage de VM (socle shares - F14, R21). Idempotent."""
    try:
        await network_port.detach_vm_from_project(VmRef(vm_id), project_id)
    except NetworkUnavailable:
        raise upstream_unavailable("Reseau") from None
    except NetworkError:
        pass
    network_ids = select(Network.id).where(Network.project_id == project_id)
    db.execute(delete(NetworkVm).where(NetworkVm.vm_id == vm_id, NetworkVm.network_id.in_(network_ids)))
    db.commit()


async def delete_project_networks(
    db: Session,
    network_port: NetworkPort,
    *,
    project_id: str,
) -> None:
    """Appele lors de la suppression d'un projet en cascade (ZUCHUON - F12, R23). Idempotent."""
    project_networks = db.scalars(select(Network).where(Network.project_id == project_id)).all()
    for net in project_networks:
        try:
            await network_port.delete_network(NetworkRef(net.id))
        except NetworkUnavailable:
            raise upstream_unavailable("Reseau") from None
        except NetworkError:
            pass
        db.delete(net)
    db.commit()


def list_vm_networks(
    db: Session,
    *,
    vm_id: str,
    project_id: str | None = None,
) -> list[Network]:
    """Retourne la liste des reseaux auxquels une VM est actuellement rattachee."""
    statement = (
        select(Network)
        .join(NetworkVm, Network.id == NetworkVm.network_id)
        .where(NetworkVm.vm_id == vm_id)
    )
    if project_id is not None:
        statement = statement.where(Network.project_id == project_id)
    return list(db.scalars(statement).all())
