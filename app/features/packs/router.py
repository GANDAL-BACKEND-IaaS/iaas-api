"""Routes des packs. Proprietaire : NAOMI. La mutation est reservee a l'administrateur."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.application.ports.iam import Identity
from app.application.ports.notifications import NotificationsPort
from app.core.database import get_db
from app.core.dependencies import get_notifications
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity, require_admin
from app.features.packs import service
from app.features.packs.schemas import PackIn, PackOut, PackUpdateIn

router = APIRouter(tags=["packs"])

_ADMIN = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT,
    ErrorCode.VALIDATION_ERROR,
    ErrorCode.NOT_IMPLEMENTED,
)


@router.get(
    "/packs",
    response_model=Page[PackOut],
    operation_id="list_packs",
    summary="Lister les packs",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR, ErrorCode.NOT_IMPLEMENTED),
)
def list_packs(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[PackOut]:
    """F17 : catalogue des packs proposes a la creation d'une VM."""
    return service.list_packs(db, identity, params)


@router.post(
    "/admin/packs",
    response_model=PackOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_pack",
    summary="Creer un pack",
    responses=error_responses(*_ADMIN),
)
def create_pack(
    body: PackIn,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PackOut:
    """F17 : definit un pack (RAM, CPU, VRAM, SSD)."""
    return service.create_pack(db, identity, body)


@router.patch(
    "/admin/packs/{pack_id}",
    response_model=PackOut,
    operation_id="update_pack",
    summary="Modifier un pack",
    responses=error_responses(*_ADMIN),
)
async def update_pack(
    pack_id: int,
    body: PackUpdateIn,
    identity: Identity = Depends(require_admin),
    notifications: NotificationsPort = Depends(get_notifications),
    db: Session = Depends(get_db),
) -> PackOut:
    """F17 : modifie un pack. Les demandes de creation en attente sont renvoyees a l'admin (R14)."""
    return await service.update_pack(db, identity, notifications, pack_id, body)


@router.delete(
    "/admin/packs/{pack_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_pack",
    summary="Supprimer un pack",
    responses=error_responses(*_ADMIN),
)
def delete_pack(
    pack_id: int,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """F17 : supprime un pack s'il ne porte aucune demande de creation en attente (R14)."""
    service.delete_pack(db, identity, pack_id)
