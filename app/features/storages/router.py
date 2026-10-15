"""Routes stockage orientees ressource. Proprietaire : TABA.

F8, F9 deposent une demande via le moteur partage ; F15 et F16 se font ensuite sur
/api/v1/requests. Le retrait d'un partage se fait sur /api/v1/shares/{share_id}/revoke.
"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.storage import StoragePort
from app.core.database import get_db
from app.core.dependencies import get_iam
from app.core.dependencies import get_storage as get_storage_port
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.requests.schemas import RequestOut
from app.features.shares.schemas import ShareOut
from app.features.storages import service
from app.features.storages.schemas import (
    ConfirmIn,
    ShareTargetIn,
    StorageOut,
    StorageRequestCreateIn,
    StorageRequestUpdateIn,
)
from app.shared.enums import ShareStatus

router = APIRouter(prefix="/projects/{project_id}/storages", tags=["stockages"])

_READ = (
    ErrorCode.UNAUTHORIZED,
    ErrorCode.FORBIDDEN,
    ErrorCode.NOT_FOUND,
    ErrorCode.VALIDATION_ERROR,
)
_REQUEST = (*_READ, ErrorCode.BAD_REQUEST, ErrorCode.CONFLICT, ErrorCode.INVALID_STATE)
_DELETE = (*_READ, ErrorCode.BAD_REQUEST, ErrorCode.UPSTREAM_UNAVAILABLE)
_SHARE = (*_READ, ErrorCode.BAD_REQUEST, ErrorCode.CONFLICT, ErrorCode.INVALID_STATE)


def _out(storage, project_id: str) -> StorageOut:
    """Schema sortant d'un stockage vu depuis `project_id` (indicateur `shared`)."""
    out = StorageOut.model_validate(storage)
    out.shared = storage.origin_project_id != project_id
    return out


@router.post(
    "",
    response_model=RequestOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="request_create_storage",
    summary="Demander la creation d'un stockage",
    description="F8 : cree une demande en attente (kind storage_create), traitee par un "
    "administrateur. Droit storage.request_create ou proprietaire.",
    responses=error_responses(*_REQUEST),
)
async def request_create_storage(
    project_id: str,
    body: StorageRequestCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """F8 : depose une demande de creation liee au projet."""
    row = await service.request_create_storage(db, iam, identity, project_id, body)
    return RequestOut.model_validate(row)


@router.get(
    "",
    response_model=Page[StorageOut],
    operation_id="list_storages",
    summary="Consulter les stockages",
    description="F10 : stockages du projet et stockages partages vers lui (`shared: true`).",
    responses=error_responses(*_READ),
)
async def list_storages(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[StorageOut]:
    """F10 : liste paginee des stockages visibles dans le projet."""
    rows, total = await service.list_storages(db, iam, identity, project_id, params)
    return Page[StorageOut](
        items=[_out(row, project_id) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get(
    "/{storage_id}",
    response_model=StorageOut,
    operation_id="get_storage",
    summary="Consulter un stockage",
    responses=error_responses(*_READ),
)
async def get_storage(
    project_id: str,
    storage_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> StorageOut:
    """F10 : consulte un stockage visible dans le projet."""
    storage = await service.get_storage(db, iam, identity, project_id, storage_id)
    return _out(storage, project_id)


@router.post(
    "/{storage_id}/update-requests",
    response_model=RequestOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="request_update_storage",
    summary="Demander la modification d'un stockage",
    description="F9 : demande en attente (kind storage_update) portant uniquement sur la taille.",
    responses=error_responses(*_REQUEST),
)
async def request_update_storage(
    project_id: str,
    storage_id: str,
    body: StorageRequestUpdateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> RequestOut:
    """F9 : depose une demande de nouvelle taille."""
    row = await service.request_update_storage(db, iam, identity, project_id, storage_id, body)
    return RequestOut.model_validate(row)


@router.post(
    "/{storage_id}/deletion",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_storage",
    summary="Supprimer un stockage",
    description="F11 : action directe, meme si le stockage contient des donnees. Sans "
    "`confirm: true`, renvoie bad_request avec l'avertissement. Revoque les partages.",
    responses=error_responses(*_DELETE),
)
async def delete_storage(
    project_id: str,
    storage_id: str,
    body: ConfirmIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    storage_port: StoragePort = Depends(get_storage_port),
    db: Session = Depends(get_db),
) -> Response:
    """F11 : supprime le stockage apres confirmation et revoque ses partages."""
    await service.delete_storage(
        db, iam, storage_port, identity, project_id, storage_id, body.confirm
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{storage_id}/shares",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="share_storage",
    summary="Partager un stockage",
    description="F14 : depuis le projet d'origine, vers un projet du meme proprietaire. "
    "Actif immediatement, sans administrateur.",
    responses=error_responses(*_SHARE),
)
async def share_storage(
    project_id: str,
    storage_id: str,
    body: ShareTargetIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ShareOut:
    """F14 : partage le stockage avec un autre projet du meme proprietaire."""
    row = await service.share_storage(
        db, iam, identity, project_id, storage_id, body.dest_project_id
    )
    return ShareOut.model_validate(row)


@router.get(
    "/{storage_id}/shares",
    response_model=Page[ShareOut],
    operation_id="list_storage_shares",
    summary="Lister les partages d'un stockage",
    responses=error_responses(*_READ),
)
async def list_storage_shares(
    project_id: str,
    storage_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    share_status: ShareStatus | None = Query(default=None, alias="status"),
) -> Page[ShareOut]:
    """Partages du stockage (actifs et revoques), filtrables par statut."""
    rows, total = await service.list_storage_shares(
        db, iam, identity, project_id, storage_id, params, share_status
    )
    return Page[ShareOut](
        items=[ShareOut.model_validate(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )
