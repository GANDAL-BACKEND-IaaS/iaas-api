"""Routes des packs. La mutation est reservee a l'administrateur."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.application.ports.iam import Identity
from app.application.ports.notifications import NotificationsPort
from app.core.database import get_db
from app.core.dependencies import get_notifications
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity, require_admin
from app.features.packs import service
from app.features.packs.schemas import PackCreateIn, PackOut, PackUpdateIn

router = APIRouter(tags=["packs"])

_ADMIN = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT,
    ErrorCode.VALIDATION_ERROR,
)


@router.get(
    "/packs",
    response_model=Page[PackOut],
    operation_id="list_packs",
    summary="Lister les packs",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR),
)
def list_packs(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    name: str | None = Query(default=None, max_length=64),
    min_ram_gb: int | None = Query(default=None, ge=0),
    max_ram_gb: int | None = Query(default=None, ge=0),
    min_vcpu: int | None = Query(default=None, ge=0),
    max_vcpu: int | None = Query(default=None, ge=0),
) -> Page[PackOut]:
    """F17 : catalogue filtre des packs proposes a la creation d'une VM."""
    return service.list_packs(
        db,
        params,
        name=name,
        min_ram_gb=min_ram_gb,
        max_ram_gb=max_ram_gb,
        min_vcpu=min_vcpu,
        max_vcpu=max_vcpu,
    )


@router.get(
    "/packs/{pack_id}",
    response_model=PackOut,
    operation_id="get_pack",
    summary="Lire un pack",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.NOT_FOUND),
)
def get_pack(
    pack_id: str,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> PackOut:
    """F17 : lecture d'un pack du catalogue."""
    return PackOut.model_validate(service.get_pack(db, pack_id))


@router.post(
    "/admin/packs",
    response_model=PackOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_pack",
    summary="Creer un pack",
    responses=error_responses(*_ADMIN),
)
def create_pack(
    body: PackCreateIn,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PackOut:
    """F17 : definit un pack (RAM, vCPU, VRAM, SSD)."""
    return PackOut.model_validate(service.create_pack(db, body))


@router.patch(
    "/admin/packs/{pack_id}",
    response_model=PackOut,
    operation_id="update_pack",
    summary="Modifier un pack",
    responses=error_responses(*_ADMIN),
)
async def update_pack(
    pack_id: str,
    body: PackUpdateIn,
    identity: Identity = Depends(require_admin),
    notifications: NotificationsPort = Depends(get_notifications),
    db: Session = Depends(get_db),
) -> PackOut:
    """F17 : modifie un pack. Les demandes de creation en attente sont mises a jour (R14)."""
    return PackOut.model_validate(
        await service.update_pack(db, identity, notifications, pack_id, body)
    )


@router.delete(
    "/admin/packs/{pack_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_pack",
    summary="Supprimer un pack",
    responses=error_responses(*_ADMIN),
)
def delete_pack(
    pack_id: str,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """F17 : supprime un pack s'il ne porte aucune demande de creation en attente (R14)."""
    service.delete_pack(db, pack_id)
