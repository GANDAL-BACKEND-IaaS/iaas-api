"""Routes du moteur de partages, versionnees par le routeur /api/v1.

La creation est immediate et n'appelle aucun groupe externe (R20).
Le retrait peut appeler le groupe Reseau si une VM etait en reseau.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort
from app.core.database import get_db
from app.core.dependencies import get_iam, get_network
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.shares import service
from app.features.shares.schemas import ShareCreateIn, ShareOut

router = APIRouter(prefix="/shares", tags=["partages"])

_CREATE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.CONFLICT,
    ErrorCode.INVALID_STATE,
    ErrorCode.VALIDATION_ERROR,
)
_READ = (ErrorCode.UNAUTHORIZED, ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR)
_REVOKE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.INVALID_STATE,
    ErrorCode.UPSTREAM_UNAVAILABLE,
)


@router.post(
    "",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_share",
    summary="Partager une ressource",
    description="Rend la ressource visible dans un autre projet du meme proprietaire (F14, R15).",
    responses=error_responses(*_CREATE),
)
async def create_share(
    body: ShareCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ShareOut:
    """Cree un partage actif immediatement, sans validation administrateur (R20)."""
    row = await service.create_share(
        db,
        iam,
        user_id=identity.user_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        dest_project_id=body.dest_project_id,
    )
    return ShareOut.model_validate(row)


@router.get(
    "",
    response_model=Page[ShareOut],
    operation_id="list_shares",
    summary="Lister les partages",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR),
)
async def list_shares(
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[ShareOut]:
    """Liste paginee des partages accessibles a l'appelant."""
    rows, total = await service.list_shares(
        db,
        iam,
        actor_id=identity.user_id,
        actor_role=identity.role,
        params=params,
    )
    return Page[ShareOut](
        items=[ShareOut.model_validate(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/{share_id}",
    response_model=ShareOut,
    operation_id="get_share",
    summary="Consulter un partage",
    responses=error_responses(*_READ),
)
async def get_share(
    share_id: int,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ShareOut:
    """Retourne un partage si l'appelant est membre d'un des projets concernes."""
    row = await service.get_share(
        db,
        iam,
        actor_id=identity.user_id,
        actor_role=identity.role,
        share_id=share_id,
    )
    return ShareOut.model_validate(row)


@router.post(
    "/{share_id}/revoke",
    response_model=ShareOut,
    operation_id="revoke_share",
    summary="Retirer un partage",
    description="Reserve au proprietaire du projet d'origine ou a l'auteur du partage (R18).",
    responses=error_responses(*_REVOKE),
)
async def revoke_share(
    share_id: int,
    identity: Identity = Depends(get_current_identity),
    network: NetworkPort = Depends(get_network),
    db: Session = Depends(get_db),
) -> ShareOut:
    """Revoque un partage actif. Une VM quitte les reseaux du projet destinataire."""
    row = await service.revoke_share(db, network, user_id=identity.user_id, share_id=share_id)
    return ShareOut.model_validate(row)
