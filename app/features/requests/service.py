"""Moteur des demandes : depot, annulation, decision et mise a jour liee aux packs.

Regles portees ici : R1, R2, R3, R4, R5, R13, R14, F15, F16.
Les handlers techniques sont injectes par kind et ne doivent pas committer eux-memes.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.hypervisor import HypervisorPort, HypervisorUnavailable, VmRef, VmSpec
from app.application.ports.iam import GlobalRole, IamPort
from app.application.ports.notifications import Notification, NotificationsPort
from app.application.ports.storage import StoragePort, StorageRef, StorageSpec, StorageUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import PageParams, paginate
from app.features.requests.schemas import (
    StorageCreatePayload,
    StorageUpdatePayload,
    VmCreatePayload,
    VmUpdatePayload,
)
from app.shared.enums import RequestKind, RequestStatus, ResourceType, StorageState, VmState
from app.shared.models.packs import Pack
from app.shared.models.projects import Project
from app.shared.models.requests import ResourceRequest
from app.shared.models.storages import Storage
from app.shared.models.vms import Vm
from app.shared.policies.access import ResourceView, authorize
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

_RIGHT_FOR_KIND = {
    RequestKind.VM_CREATE: "vm.request_create",
    RequestKind.VM_UPDATE: "vm.request_update",
    RequestKind.STORAGE_CREATE: "storage.request_create",
    RequestKind.STORAGE_UPDATE: "storage.request_update",
}

Handler = Callable[["RequestContext"], Awaitable[None]]
_HANDLERS: dict[str, Handler] = {}


@dataclass
class RequestContext:
    """Contexte passe a un handler : demande, session et ports techniques."""

    db: Session
    request: ResourceRequest
    hypervisor: HypervisorPort
    storage: StoragePort


def register_handler(kind: RequestKind, handler: Handler) -> None:
    """Associe le traitement technique d'un kind de demande."""
    _HANDLERS[kind.value] = handler


def clear_handlers() -> None:
    """Retire tous les handlers. Utile aux tests."""
    _HANDLERS.clear()


def _validation(exc: ValidationError) -> AppError:
    return AppError(ErrorCode.VALIDATION_ERROR, "Charge utile invalide.", details=exc.errors())


def _get_request(db: Session, request_id: int) -> ResourceRequest:
    row = db.get(ResourceRequest, request_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Demande introuvable.")
    return row


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


def _normalize_vm_create(db: Session, payload: dict) -> dict:
    try:
        data = VmCreatePayload.model_validate(payload)
    except ValidationError as exc:
        raise _validation(exc) from None
    custom = [data.ram, data.cpu, data.vram, data.ssd]
    has_custom = any(value is not None for value in custom)
    if data.pack_id is not None and has_custom:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "Choisir un pack ou une configuration personnalisee, pas les deux.",
        )
    if data.pack_id is not None:
        pack = db.get(Pack, data.pack_id)
        if pack is None:
            raise AppError(ErrorCode.NOT_FOUND, "Pack introuvable.")
        return {
            "name": data.name,
            "pack_id": pack.id,
            "ram": pack.ram,
            "cpu": pack.cpu,
            "vram": pack.vram,
            "ssd": pack.ssd,
        }
    if any(value is None for value in custom):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "La configuration personnalisee exige ram, cpu, vram et ssd.",
        )
    return data.model_dump()


def _normalize_vm_update(payload: dict) -> dict:
    try:
        data = VmUpdatePayload.model_validate(payload)
    except ValidationError as exc:
        raise _validation(exc) from None
    if all(value is None for value in (data.ram, data.cpu, data.vram, data.ssd)):
        raise AppError(ErrorCode.VALIDATION_ERROR, "Au moins une caracteristique doit etre fournie.")
    return data.model_dump()


def _normalize_storage_create(payload: dict) -> dict:
    try:
        return StorageCreatePayload.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise _validation(exc) from None


def _normalize_storage_update(payload: dict) -> dict:
    try:
        return StorageUpdatePayload.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise _validation(exc) from None


def _prepare(db: Session, kind: RequestKind, payload: dict, target_resource_id: str | None):
    """Valide la charge et retourne (payload normalise, type cible, vue ressource ou None)."""
    if kind == RequestKind.VM_CREATE:
        if target_resource_id is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Une creation ne cible pas une ressource existante.")
        return _normalize_vm_create(db, payload), None, None
    if kind == RequestKind.STORAGE_CREATE:
        if target_resource_id is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Une creation ne cible pas une ressource existante.")
        return _normalize_storage_create(payload), None, None
    if target_resource_id is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, "La modification exige target_resource_id.")
    if kind == RequestKind.VM_UPDATE:
        vm = db.get(Vm, target_resource_id)
        if vm is None:
            raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")
        if vm.state == VmState.DELETING.value:
            raise AppError(ErrorCode.INVALID_STATE, "La VM est en cours de suppression.")
        view = ResourceView(ResourceType.VM.value, vm.id, vm.origin_project_id)
        return _normalize_vm_update(payload), ResourceType.VM.value, view
    storage = db.get(Storage, target_resource_id)
    if storage is None:
        raise AppError(ErrorCode.NOT_FOUND, "Stockage introuvable.")
    if storage.state == StorageState.DELETING.value:
        raise AppError(ErrorCode.INVALID_STATE, "Le stockage est en cours de suppression.")
    view = ResourceView(ResourceType.STORAGE.value, storage.id, storage.origin_project_id)
    return _normalize_storage_update(payload), ResourceType.STORAGE.value, view


async def submit_request(
    db: Session,
    iam: IamPort,
    *,
    author_id: str,
    project_id: str,
    kind: RequestKind,
    payload: dict,
    target_resource_id: str | None,
) -> ResourceRequest:
    """Enregistre une demande en attente apres controle des droits (R1, R2, R13)."""
    _require_project(db, project_id)
    normalized, target_type, view = _prepare(db, kind, payload, target_resource_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=author_id,
        project_id=project_id,
        required_right=_RIGHT_FOR_KIND[kind],
        resource=view,
    )
    row = ResourceRequest(
        project_id=project_id,
        author_id=author_id,
        kind=kind.value,
        status=RequestStatus.PENDING.value,
        payload=normalized,
        target_resource_type=target_type,
        target_resource_id=target_resource_id,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor_id=author_id,
        action="request.submitted",
        entity_type="request",
        entity_id=str(row.id),
        data={"kind": kind.value, "project_id": project_id},
    )
    db.commit()
    db.refresh(row)
    return row


def cancel_request(db: Session, *, author_id: str, request_id: int) -> ResourceRequest:
    """Annule une demande en attente. Seul l'auteur peut le faire (R5, F15)."""
    row = _get_request(db, request_id)
    if row.author_id != author_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul l'auteur peut annuler la demande.")
    if row.status != RequestStatus.PENDING.value:
        raise AppError(ErrorCode.INVALID_STATE, "Seule une demande en attente peut etre annulee.")
    row.status = RequestStatus.CANCELLED.value
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=author_id,
        action="request.cancelled",
        entity_type="request",
        entity_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    return row


async def _notify(notifications: NotificationsPort, user_id: str, subject: str, message: str) -> None:
    """Notifie sans faire echouer la decision deja enregistree."""
    try:
        await notifications.notify(Notification(user_id=user_id, subject=subject, message=message))
    except Exception:
        logger.warning("Notification non delivree pour %s.", user_id)


def _require_admin(role: GlobalRole) -> None:
    if role != GlobalRole.ADMIN:
        raise AppError(ErrorCode.FORBIDDEN, "Reserve aux administrateurs.")


def _require_pending(row: ResourceRequest) -> None:
    if row.status != RequestStatus.PENDING.value:
        raise AppError(ErrorCode.INVALID_STATE, "Seule une demande en attente peut etre traitee.")


async def accept_request(
    db: Session,
    *,
    actor_id: str,
    actor_role: GlobalRole,
    request_id: int,
    note: str | None,
    hypervisor: HypervisorPort,
    storage: StoragePort,
    notifications: NotificationsPort,
) -> ResourceRequest:
    """Accepte une demande sans la modifier, puis appelle le handler du kind (R3, F16)."""
    _require_admin(actor_role)
    row = _get_request(db, request_id)
    _require_pending(row)
    handler = _HANDLERS.get(row.kind)
    if handler is None:
        raise AppError(
            ErrorCode.NOT_IMPLEMENTED,
            f"Aucun traitement technique n'est enregistre pour {row.kind}.",
        )
    context = RequestContext(db=db, request=row, hypervisor=hypervisor, storage=storage)
    try:
        await handler(context)
    except AppError:
        db.rollback()
        raise
    except (HypervisorUnavailable, StorageUnavailable):
        db.rollback()
        raise upstream_unavailable("infrastructure") from None
    except Exception:
        db.rollback()
        raise upstream_unavailable("infrastructure") from None
    row.status = RequestStatus.ACCEPTED.value
    row.admin_note = note
    row.decided_at = utcnow()
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=actor_id,
        action="request.accepted",
        entity_type="request",
        entity_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    await _notify(
        notifications,
        row.author_id,
        "Demande acceptee",
        f"La demande {row.id} a ete acceptee.",
    )
    return row


async def refuse_request(
    db: Session,
    *,
    actor_id: str,
    actor_role: GlobalRole,
    request_id: int,
    note: str | None,
    notifications: NotificationsPort,
) -> ResourceRequest:
    """Refuse une demande sans la modifier. La remarque reste optionnelle (R3, R4, F16)."""
    _require_admin(actor_role)
    row = _get_request(db, request_id)
    _require_pending(row)
    row.status = RequestStatus.REFUSED.value
    row.admin_note = note
    row.decided_at = utcnow()
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=actor_id,
        action="request.refused",
        entity_type="request",
        entity_id=str(row.id),
    )
    db.commit()
    db.refresh(row)
    await _notify(
        notifications,
        row.author_id,
        "Demande refusee",
        f"La demande {row.id} a ete refusee.",
    )
    return row


def get_request(db: Session, *, actor_id: str, actor_role: GlobalRole, request_id: int) -> ResourceRequest:
    """Retourne une demande visible par son auteur ou par un administrateur."""
    row = _get_request(db, request_id)
    if actor_role != GlobalRole.ADMIN and row.author_id != actor_id:
        raise AppError(ErrorCode.FORBIDDEN, "Cette demande ne vous est pas accessible.")
    return row


def list_requests(
    db: Session,
    *,
    actor_id: str,
    actor_role: GlobalRole,
    params: PageParams,
    status: RequestStatus | None = None,
) -> tuple[list[ResourceRequest], int]:
    """Liste paginee. Un administrateur voit tout, un utilisateur voit les siennes."""
    statement = select(ResourceRequest).order_by(ResourceRequest.created_at.desc())
    if actor_role != GlobalRole.ADMIN:
        statement = statement.where(ResourceRequest.author_id == actor_id)
    if status is not None:
        statement = statement.where(ResourceRequest.status == status.value)
    rows, total = paginate(db, statement, params)
    return list(rows), total


async def refresh_pending_vm_creates(
    db: Session,
    *,
    actor_id: str,
    pack: Pack,
    notifications: NotificationsPort,
) -> list[ResourceRequest]:
    """Met a jour les demandes de creation en attente qui reposent sur ce pack (R14).

    Elles restent en attente : l'administrateur doit les valider a nouveau.
    Les VM deja creees ne sont pas modifiees.
    """
    statement = select(ResourceRequest).where(
        ResourceRequest.kind == RequestKind.VM_CREATE.value,
        ResourceRequest.status == RequestStatus.PENDING.value,
    )
    touched: list[ResourceRequest] = []
    for row in db.scalars(statement):
        if row.payload.get("pack_id") != pack.id:
            continue
        updated = dict(row.payload)
        updated["ram"] = pack.ram
        updated["cpu"] = pack.cpu
        updated["vram"] = pack.vram
        updated["ssd"] = pack.ssd
        row.payload = updated
        row.updated_at = utcnow()
        record_audit(
            db,
            actor_id=actor_id,
            action="request.pack_refreshed",
            entity_type="request",
            entity_id=str(row.id),
            data={"pack_id": pack.id},
        )
        touched.append(row)
    db.commit()
    for row in touched:
        db.refresh(row)
        await _notify(
            notifications,
            row.author_id,
            "Demande mise a jour",
            f"La demande {row.id} a ete mise a jour suite a la modification du pack.",
        )
    return touched


async def handle_vm_create(context: RequestContext) -> None:
    """Cree la VM via l'hyperviseur puis l'enregistre dans le projet de la demande."""
    payload = context.request.payload
    try:
        ref = await context.hypervisor.create_vm(
            VmSpec(payload["name"], payload["ram"], payload["cpu"], payload["vram"], payload["ssd"])
        )
    except HypervisorUnavailable:
        raise upstream_unavailable("Hyperviseur") from None
    context.db.add(
        Vm(
            id=ref.vm_id,
            origin_project_id=context.request.project_id,
            name=payload["name"],
            ram=payload["ram"],
            cpu=payload["cpu"],
            vram=payload["vram"],
            ssd=payload["ssd"],
            pack_id=payload.get("pack_id"),
            state=VmState.STOPPED.value,
        )
    )


async def handle_vm_update(context: RequestContext) -> None:
    """Applique les caracteristiques demandees, sans en inventer d'autres (R3)."""
    vm = context.db.get(Vm, context.request.target_resource_id)
    if vm is None:
        raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")
    for field in ("ram", "cpu", "vram", "ssd"):
        value = context.request.payload.get(field)
        if value is not None:
            setattr(vm, field, value)
    try:
        await context.hypervisor.update_vm(
            VmRef(vm.id), VmSpec(vm.name, vm.ram, vm.cpu, vm.vram, vm.ssd)
        )
    except HypervisorUnavailable:
        raise upstream_unavailable("Hyperviseur") from None


async def handle_storage_create(context: RequestContext) -> None:
    """Cree le stockage via le groupe Stockage puis l'enregistre dans le projet."""
    payload = context.request.payload
    try:
        ref = await context.storage.create_storage(StorageSpec(payload["name"], payload["size"]))
    except StorageUnavailable:
        raise upstream_unavailable("Stockage") from None
    context.db.add(
        Storage(
            id=ref.storage_id,
            origin_project_id=context.request.project_id,
            name=payload["name"],
            size=payload["size"],
            state=StorageState.AVAILABLE.value,
        )
    )


async def handle_storage_update(context: RequestContext) -> None:
    """Modifie uniquement la taille du stockage (F9, R3)."""
    storage = context.db.get(Storage, context.request.target_resource_id)
    if storage is None:
        raise AppError(ErrorCode.NOT_FOUND, "Stockage introuvable.")
    storage.size = context.request.payload["size"]
    try:
        await context.storage.resize(StorageRef(storage.id), storage.size)
    except StorageUnavailable:
        raise upstream_unavailable("Stockage") from None


def register_default_handlers() -> None:
    """Enregistre les traitements techniques par defaut, adosses aux ports."""
    register_handler(RequestKind.VM_CREATE, handle_vm_create)
    register_handler(RequestKind.VM_UPDATE, handle_vm_update)
    register_handler(RequestKind.STORAGE_CREATE, handle_storage_create)
    register_handler(RequestKind.STORAGE_UPDATE, handle_storage_update)
