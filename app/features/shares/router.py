"""Routes du moteur de partages.

Ressources : un partage est cree depuis la route de la ressource d'origine.
Extensions conservees : liste globale et lecture unitaire des partages de l'appelant.
Aucun acces administrateur global : seul le membership donne acces.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort
from app.core.database import get_db
from app.core.dependencies import get_iam, get_network
from app.core.errors import ErrorCode, error_responses
from app.core.pagination import Page, PageParams, get_page_params
from app.features.auth.dependencies import get_current_identity
from app.features.shares import service
from app.features.shares.schemas import ShareCreateIn, ShareOut, ShareRevokeOut
from app.shared.enums import ResourceType, ShareStatus

router = APIRouter(tags=["partages"])
extensions = APIRouter(tags=["partages (extension)"])

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


@router.get(
    "/projects/{project_id}/shares",
    response_model=Page[ShareOut],
    operation_id="list_project_shares",
    summary="Lister les partages recus par un projet",
    responses=error_responses(*_READ),
)
async def list_project_shares(
    project_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    resource_type: ResourceType | None = Query(default=None),
    share_status: ShareStatus = Query(default=ShareStatus.ACTIVE, alias="status"),
) -> Page[ShareOut]:
    """Partages dont le projet de la route est le destinataire (actifs par defaut)."""
    rows, total = await service.list_received(
        db,
        iam,
        user_id=identity.user_id,
        project_id=project_id,
        params=params,
        resource_type=resource_type,
        status=share_status,
    )
    return Page.build([ShareOut.model_validate(row) for row in rows], total, params)


@router.post(
    "/projects/{project_id}/storages/{storage_id}/shares",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="share_storage",
    summary="Partager un stockage",
    responses=error_responses(*_CREATE),
)
async def share_storage(
    project_id: str,
    storage_id: str,
    body: ShareCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ShareOut:
    """Cree un partage actif depuis le projet d'origine du stockage."""
    row = await service.create_share(
        db,
        iam,
        user_id=identity.user_id,
        project_id=project_id,
        resource_type=ResourceType.STORAGE,
        resource_id=storage_id,
        dest_project_id=body.dest_project_id,
    )
    return ShareOut.model_validate(row)


@router.get(
    "/projects/{project_id}/storages/{storage_id}/shares",
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
    dest_project_id: str | None = Query(default=None),
) -> Page[ShareOut]:
    """Partages emis pour ce stockage, filtrables par etat et destinataire."""
    rows, total = await service.list_for_resource(
        db,
        iam,
        user_id=identity.user_id,
        project_id=project_id,
        resource_type=ResourceType.STORAGE,
        resource_id=storage_id,
        params=params,
        status=share_status,
        dest_project_id=dest_project_id,
    )
    return Page.build([ShareOut.model_validate(row) for row in rows], total, params)


@router.post(
    "/projects/{project_id}/vms/{vm_id}/shares",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="share_vm",
    summary="Partager une VM",
    responses=error_responses(*_CREATE),
)
async def share_vm(
    project_id: str,
    vm_id: str,
    body: ShareCreateIn,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ShareOut:
    """Cree un partage actif depuis le projet d'origine de la VM."""
    row = await service.create_share(
        db,
        iam,
        user_id=identity.user_id,
        project_id=project_id,
        resource_type=ResourceType.VM,
        resource_id=vm_id,
        dest_project_id=body.dest_project_id,
    )
    return ShareOut.model_validate(row)


@router.get(
    "/projects/{project_id}/vms/{vm_id}/shares",
    response_model=Page[ShareOut],
    operation_id="list_vm_shares",
    summary="Lister les partages d'une VM",
    responses=error_responses(*_READ),
)
async def list_vm_shares(
    project_id: str,
    vm_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
    share_status: ShareStatus | None = Query(default=None, alias="status"),
    dest_project_id: str | None = Query(default=None),
) -> Page[ShareOut]:
    """Partages emis pour cette VM, filtrables par etat et destinataire."""
    rows, total = await service.list_for_resource(
        db,
        iam,
        user_id=identity.user_id,
        project_id=project_id,
        resource_type=ResourceType.VM,
        resource_id=vm_id,
        params=params,
        status=share_status,
        dest_project_id=dest_project_id,
    )
    return Page.build([ShareOut.model_validate(row) for row in rows], total, params)


@router.post(
    "/shares/{share_id}/revoke",
    response_model=ShareRevokeOut,
    operation_id="revoke_share",
    summary="Revoquer un partage",
    responses=error_responses(*_REVOKE),
)
async def revoke_share(
    share_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    network: NetworkPort = Depends(get_network),
    db: Session = Depends(get_db),
) -> ShareRevokeOut:
    """Revoque un partage actif. Une VM quitte les reseaux du projet destinataire."""
    row = await service.revoke_share(
        db, network, iam, user_id=identity.user_id, share_id=share_id
    )
    return ShareRevokeOut(
        share=ShareOut.model_validate(row),
        message="Le partage a ete revoque.",
    )


@extensions.get(
    "/shares",
    response_model=Page[ShareOut],
    operation_id="list_shares",
    summary="Lister mes partages (extension)",
    responses=error_responses(ErrorCode.UNAUTHORIZED, ErrorCode.VALIDATION_ERROR),
)
async def list_shares(
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
    params: PageParams = Depends(get_page_params),
) -> Page[ShareOut]:
    """Partages des projets dont l'appelant est membre. Aucun bypass administrateur."""
    rows, total = await service.list_shares(
        db, iam, user_id=identity.user_id, params=params
    )
    return Page.build([ShareOut.model_validate(row) for row in rows], total, params)


@extensions.get(
    "/shares/{share_id}",
    response_model=ShareOut,
    operation_id="get_share",
    summary="Consulter un de mes partages (extension)",
    responses=error_responses(*_READ),
)
async def get_share(
    share_id: str,
    identity: Identity = Depends(get_current_identity),
    iam: IamPort = Depends(get_iam),
    db: Session = Depends(get_db),
) -> ShareOut:
    """Retourne un partage si l'appelant est membre d'un des projets concernes."""
    row = await service.get_share(db, iam, user_id=identity.user_id, share_id=share_id)
    return ShareOut.model_validate(row)
