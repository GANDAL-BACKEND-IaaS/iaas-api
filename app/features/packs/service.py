"""Services des packs. Proprietaire : NAOMI.

La modification d'un pack renvoie les demandes de creation en attente a l'administrateur (R14).
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.ports.iam import GlobalRole, Identity
from app.application.ports.notifications import NotificationsPort
from app.core.errors import AppError, ErrorCode
from app.core.pagination import Page, PageParams, paginate
from app.features.packs.schemas import PackIn, PackOut, PackUpdateIn
from app.features.requests.service import refresh_pending_vm_creates
from app.shared.enums import RequestKind, RequestStatus
from app.shared.models.packs import Pack
from app.shared.models.requests import ResourceRequest


def _require_admin(identity: Identity) -> None:
    if identity.role != GlobalRole.ADMIN:
        raise AppError(ErrorCode.FORBIDDEN, "Reserve aux administrateurs.")


def _get(db: Session, pack_id: int) -> Pack:
    pack = db.get(Pack, pack_id)
    if pack is None:
        raise AppError(ErrorCode.NOT_FOUND, "Pack introuvable.")
    return pack


def list_packs(db: Session, _identity: Identity, params: PageParams) -> Page[PackOut]:
    """F17 : liste le catalogue de packs."""
    rows, total = paginate(db, select(Pack).order_by(Pack.name), params)
    return Page[PackOut](
        items=[PackOut.model_validate(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


def create_pack(db: Session, identity: Identity, body: PackIn) -> Pack:
    """F17 : cree un pack. Reserve a un administrateur."""
    _require_admin(identity)
    pack = Pack(name=body.name, ram=body.ram, cpu=body.cpu, vram=body.vram, ssd=body.ssd)
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
    pack_id: int,
    body: PackUpdateIn,
) -> Pack:
    """F17 : modifie un pack et met a jour les demandes de creation en attente (R14)."""
    _require_admin(identity)
    pack = _get(db, pack_id)
    for field in ("name", "ram", "cpu", "vram", "ssd"):
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


def delete_pack(db: Session, identity: Identity, pack_id: int) -> None:
    """F17 : supprime un pack seulement s'il ne porte aucune demande de creation en attente."""
    _require_admin(identity)
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
