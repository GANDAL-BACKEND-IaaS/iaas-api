"""Services des packs.

La modification d'un pack renvoie les demandes de creation en attente a l'administrateur (R14).
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.ports.iam import Identity
from app.application.ports.notifications import NotificationsPort
from app.core.errors import AppError, ErrorCode
from app.core.pagination import Page, PageParams, paginate
from app.features.packs.schemas import PackCreateIn, PackOut, PackUpdateIn
from app.features.requests.service import refresh_pending_vm_creates
from app.shared.enums import RequestKind, RequestStatus
from app.shared.models.packs import Pack
from app.shared.models.requests import ResourceRequest


def _get(db: Session, pack_id: str) -> Pack:
    pack = db.get(Pack, pack_id)
    if pack is None:
        raise AppError(ErrorCode.NOT_FOUND, "Pack introuvable.")
    return pack


def list_packs(
    db: Session,
    params: PageParams,
    *,
    name: str | None = None,
    min_ram_gb: int | None = None,
    max_ram_gb: int | None = None,
    min_vcpu: int | None = None,
    max_vcpu: int | None = None,
) -> Page[PackOut]:
    """F17 : catalogue filtre, trie par nom puis identifiant."""
    if min_ram_gb is not None and max_ram_gb is not None and min_ram_gb > max_ram_gb:
        raise AppError(ErrorCode.VALIDATION_ERROR, "min_ram_gb ne peut pas depasser max_ram_gb.")
    if min_vcpu is not None and max_vcpu is not None and min_vcpu > max_vcpu:
        raise AppError(ErrorCode.VALIDATION_ERROR, "min_vcpu ne peut pas depasser max_vcpu.")
    statement = select(Pack)
    if name:
        statement = statement.where(Pack.name.ilike(f"{name}%"))
    if min_ram_gb is not None:
        statement = statement.where(Pack.ram_gb >= min_ram_gb)
    if max_ram_gb is not None:
        statement = statement.where(Pack.ram_gb <= max_ram_gb)
    if min_vcpu is not None:
        statement = statement.where(Pack.vcpu >= min_vcpu)
    if max_vcpu is not None:
        statement = statement.where(Pack.vcpu <= max_vcpu)
    rows, total = paginate(db, statement.order_by(Pack.name, Pack.id), params)
    return Page.build([PackOut.model_validate(row) for row in rows], total, params)


def get_pack(db: Session, pack_id: str) -> Pack:
    """F17 : lecture d'un pack du catalogue."""
    return _get(db, pack_id)


def create_pack(db: Session, body: PackCreateIn) -> Pack:
    """F17 : cree un pack. Reserve a un administrateur (verifie par la route)."""
    pack = Pack(
        name=body.name,
        description=body.description,
        ram_gb=body.ram_gb,
        vcpu=body.vcpu,
        vram_gb=body.vram_gb,
        ssd_gb=body.ssd_gb,
    )
    db.add(pack)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, "Ce nom de pack existe deja.") from None
    db.refresh(pack)
    return pack


async def update_pack(
    db: Session,
    identity: Identity,
    notifications: NotificationsPort,
    pack_id: str,
    body: PackUpdateIn,
) -> Pack:
    """F17 : modifie un pack et met a jour les demandes de creation en attente (R14)."""
    pack = _get(db, pack_id)
    for field in ("name", "description", "ram_gb", "vcpu", "vram_gb", "ssd_gb"):
        value = getattr(body, field)
        if value is not None:
            setattr(pack, field, value)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, "Ce nom de pack existe deja.") from None
    await refresh_pending_vm_creates(
        db, actor_id=identity.user_id, pack=pack, notifications=notifications
    )
    db.refresh(pack)
    return pack


def delete_pack(db: Session, pack_id: str) -> None:
    """F17 : supprime un pack seulement s'il ne porte aucune demande de creation en attente."""
    pack = _get(db, pack_id)
    pending = db.scalars(
        select(ResourceRequest).where(
            ResourceRequest.kind == RequestKind.VM_CREATE.value,
            ResourceRequest.status == RequestStatus.PENDING.value,
        )
    )
    if any(row.payload.get("pack_id") == pack_id for row in pending):
        raise AppError(
            ErrorCode.CONFLICT,
            "Un pack utilise par une demande de creation en attente ne peut pas etre supprime.",
        )
    db.delete(pack)
    db.commit()
