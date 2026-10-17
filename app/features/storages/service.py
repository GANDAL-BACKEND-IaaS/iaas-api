"""Services stockage. Proprietaire : TABA (port Espaces).

Les creations et modifications de taille passent par une demande.
La suppression est directe et revoque les partages.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.network import NetworkPort
from app.application.ports.storage import StoragePort, StorageRef, StorageUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import Page, PageParams, paginate
from app.features.requests.schemas import RequestOut
from app.features.requests.service import submit_request
from app.features.shares.schemas import ShareOut
from app.features.shares.service import create_share, revoke_all_for_resource, visible_in_project
from app.features.storages.schemas import StorageOut, StorageRequestCreateIn, StorageRequestUpdateIn
from app.shared.enums import RequestKind, ResourceType
from app.shared.models.shares import ResourceShare
from app.shared.models.storages import Storage
from app.shared.policies.access import ResourceView, authorize


def _out(storage: Storage, project_id: str) -> StorageOut:
    item = StorageOut.model_validate(storage)
    return item.model_copy(update={"shared": storage.origin_project_id != project_id})


def _load(db: Session, storage_id: str) -> Storage:
    row = db.get(Storage, storage_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Stockage introuvable.")
    return row


def _visible_or_404(db: Session, row: Storage, project_id: str) -> None:
    if not visible_in_project(
        db,
        resource_type=ResourceType.STORAGE.value,
        resource_id=row.id,
        origin_project_id=row.origin_project_id,
        project_id=project_id,
    ):
        raise AppError(ErrorCode.NOT_FOUND, "Stockage introuvable.")


async def request_create_storage(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    body: StorageRequestCreateIn,
) -> RequestOut:
    """F8 : depose une demande de creation liee au projet."""
    row = await submit_request(
        db,
        iam,
        author_id=identity.user_id,
        project_id=project_id,
        kind=RequestKind.STORAGE_CREATE,
        payload=body.model_dump(),
        target_resource_id=None,
    )
    return RequestOut.model_validate(row)


async def request_update_storage(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    storage_id: str,
    body: StorageRequestUpdateIn,
) -> RequestOut:
    """F9 : depose une demande de modification de la taille."""
    row = await submit_request(
        db,
        iam,
        author_id=identity.user_id,
        project_id=project_id,
        kind=RequestKind.STORAGE_UPDATE,
        payload=body.model_dump(),
        target_resource_id=storage_id,
    )
    return RequestOut.model_validate(row)


async def list_storages(
    db: Session, iam: IamPort, identity: Identity, project_id: str, params: PageParams
) -> Page[StorageOut]:
    """F10 : liste les stockages du projet, y compris ceux qui y sont partages."""
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right="storage.view"
    )
    shared_ids = select(ResourceShare.resource_id).where(
        ResourceShare.resource_type == ResourceType.STORAGE.value,
        ResourceShare.dest_project_id == project_id,
        ResourceShare.status == "active",
    )
    statement = (
        select(Storage)
        .where(or_(Storage.origin_project_id == project_id, Storage.id.in_(shared_ids)))
        .order_by(Storage.created_at.desc())
    )
    rows, total = paginate(db, statement, params)
    return Page[StorageOut](
        items=[_out(row, project_id) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def get_storage(
    db: Session, iam: IamPort, identity: Identity, project_id: str, storage_id: str
) -> StorageOut:
    """F10 : consulte un stockage visible dans le projet."""
    row = _load(db, storage_id)
    _visible_or_404(db, row, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="storage.view",
        resource=ResourceView(ResourceType.STORAGE.value, row.id, row.origin_project_id),
    )
    return _out(row, project_id)


async def delete_storage(
    db: Session,
    iam: IamPort,
    port: StoragePort,
    identity: Identity,
    project_id: str,
    storage_id: str,
    confirm: bool,
    network: NetworkPort | None = None,
) -> None:
    """F11 : supprime le stockage apres confirmation et revoque ses partages."""
    if confirm is not True:
        raise AppError(ErrorCode.VALIDATION_ERROR, "La suppression exige une confirmation explicite.")
    row = _load(db, storage_id)
    _visible_or_404(db, row, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="storage.delete",
        resource=ResourceView(ResourceType.STORAGE.value, row.id, row.origin_project_id),
    )
    if network is not None:
        try:
            await revoke_all_for_resource(
                db,
                network,
                actor_id=identity.user_id,
                resource_type=ResourceType.STORAGE.value,
                resource_id=row.id,
            )
        except AppError:
            db.rollback()
            raise
    else:
        shares = list(
            db.scalars(
                select(ResourceShare).where(
                    ResourceShare.resource_type == ResourceType.STORAGE.value,
                    ResourceShare.resource_id == row.id,
                    ResourceShare.status == "active",
                )
            )
        )
        for share in shares:
            share.status = "revoked"
    try:
        await port.delete_storage(StorageRef(row.id))
    except (StorageUnavailable, KeyError):
        db.rollback()
        raise upstream_unavailable("Stockage") from None
    record_audit(
        db, actor_id=identity.user_id, action="storage.deleted", entity_type="storage", entity_id=row.id
    )
    db.delete(row)
    db.commit()


async def share_storage(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    storage_id: str,
    dest_project_id: str,
) -> ShareOut:
    """F14 : partage le stockage depuis son projet d'origine."""
    row = _load(db, storage_id)
    if row.origin_project_id != project_id:
        raise AppError(ErrorCode.FORBIDDEN, "Le partage se fait depuis le projet d'origine.")
    created = await create_share(
        db,
        iam,
        user_id=identity.user_id,
        resource_type=ResourceType.STORAGE,
        resource_id=storage_id,
        dest_project_id=dest_project_id,
    )
    return ShareOut.model_validate(created)
