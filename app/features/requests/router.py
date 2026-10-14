"""Routes du moteur de demandes, versionnees par le routeur /api/v1.

F15 : l'auteur annule une demande en attente.
F16 : l'administrateur accepte ou refuse, sans modifier la demande.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.application.ports.hypervisor import HypervisorPort
from app.application.ports.iam import IamPort, Identity
from app.application.ports.notifications import NotificationsPort
from app.application.ports.storage import StoragePort
from app.core.database import get_db
from app.core.dependencies import get_hypervisor, get_iam, get_notifications, get_storage
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity, require_admin
from app.features.requests import service
from app.features.requests.schemas import RequestCreateIn, RequestDecisionIn, RequestOut
from app.features.requests.service import register_default_handlers
from app.shared.enums import RequestStatus

register_default_handlers()

router = APIRouter(prefix="/requests", tags=["demandes"])

_AUTH = (ErrorCode.UNAUTHORIZED,)
_READ = (ErrorCode.UNAUTHORIZED, ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND, ErrorCode.VALIDATION_ERROR)
_SUBMIT = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.VALIDATION_ERROR,
    ErrorCode.INVALID_STATE,
)
_CANCEL = (ErrorCode.UNAUTHORIZED, ErrorCode.FORBIDDEN, ErrorCode.NOT_FOUND, ErrorCode.INVALID_STATE)
_DECIDE = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.INVALID_STATE,
    ErrorCode.NOT_IMPLEMENTED,
    ErrorCode.UPSTREAM_UNAVAILABLE,
    ErrorCode.VALIDATION_ERROR,
)


@router.post(
    "",
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="submit_request",
    summary="Deposer une demande",
    description="Cree une demande en attente, liee a un projet. Un administrateur devra la traiter.",
    responses=error_responses(*_SUBMIT),
)
async def submit_request(
    body: RequestCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """Depose une demande de creation ou de modification (R1, R2, R13)."""
    row = await service.submit_request(
        db,
        iam,
        author_id=identity.user_id,
        project_id=body.project_id,
        kind=body.kind,
        payload=body.payload,
        target_resource_id=body.target_resource_id,
    )
    return RequestOut.model_validate(row)


@router.get(
    "",
    response_model=Page[RequestOut],
    operation_id="list_requests",
    summary="Lister les demandes",
    responses=error_responses(*_AUTH, ErrorCode.VALIDATION_ERROR),
)
def list_requests(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    request_status: RequestStatus | None = Query(default=None, alias="status"),
) -> Page[RequestOut]:
    """Liste paginee des demandes de l'appelant, ou de toutes les demandes pour un admin."""
    rows, total = service.list_requests(
        db,
        actor_id=identity.user_id,
        actor_role=identity.role,
        params=params,
        status=request_status,
    )
    return Page[RequestOut](
        items=[RequestOut.model_validate(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/{request_id}",
    response_model=RequestOut,
    operation_id="get_request",
    summary="Consulter une demande",
    responses=error_responses(*_READ),
)
def get_request(
    request_id: int,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> RequestOut:
    """Retourne une demande accessible a l'appelant."""
    row = service.get_request(
        db, actor_id=identity.user_id, actor_role=identity.role, request_id=request_id
    )
    return RequestOut.model_validate(row)


@router.post(
    "/{request_id}/cancel",
    response_model=RequestOut,
    operation_id="cancel_request",
    summary="Annuler une demande",
    description="Reserve a l'auteur, et seulement tant que la demande est en attente (F15).",
    responses=error_responses(*_CANCEL),
)
def cancel_request(
    request_id: int,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> RequestOut:
    """Annule une demande en attente (F15, R5)."""
    row = service.cancel_request(db, author_id=identity.user_id, request_id=request_id)
    return RequestOut.model_validate(row)


@router.post(
    "/{request_id}/accept",
    response_model=RequestOut,
    operation_id="accept_request",
    summary="Accepter une demande",
    description="Reserve a un administrateur. La demande n'est pas modifiee (F16, R3).",
    responses=error_responses(*_DECIDE),
)
async def accept_request(
    request_id: int,
    body: RequestDecisionIn,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
    hypervisor: HypervisorPort = Depends(get_hypervisor),
    storage: StoragePort = Depends(get_storage),
    notifications: NotificationsPort = Depends(get_notifications),
) -> RequestOut:
    """Accepte une demande en attente et declenche le traitement technique (F16)."""
    row = await service.accept_request(
        db,
        actor_id=identity.user_id,
        actor_role=identity.role,
        request_id=request_id,
        note=body.note,
        hypervisor=hypervisor,
        storage=storage,
        notifications=notifications,
    )
    return RequestOut.model_validate(row)


@router.post(
    "/{request_id}/refuse",
    response_model=RequestOut,
    operation_id="refuse_request",
    summary="Refuser une demande",
    description="Reserve a un administrateur. La remarque est optionnelle (R4).",
    responses=error_responses(*_DECIDE),
)
async def refuse_request(
    request_id: int,
    body: RequestDecisionIn,
    identity: Identity = Depends(require_admin),
    db: Session = Depends(get_db),
    notifications: NotificationsPort = Depends(get_notifications),
) -> RequestOut:
    """Refuse une demande en attente sans en changer le contenu (F16, R3)."""
    row = await service.refuse_request(
        db,
        actor_id=identity.user_id,
        actor_role=identity.role,
        request_id=request_id,
        note=body.note,
        notifications=notifications,
    )
    return RequestOut.model_validate(row)
