"""Services stockage.

Les creations et modifications de taille passent par une demande.
La suppression est directe et revoque les partages.
"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.storage import StoragePort, StorageRef, StorageUnavailable
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import Page, PageParams, paginate
from app.features.requests.schemas import (
    RequestOut,
    StorageCreateRequestIn,
    StorageUpdateRequestIn,
)
from app.features.requests.service import submit_request
from app.features.shares.service import revoke_all_for_resource, visible_in_project
from app.features.storages.schemas import StorageOut
from app.shared.deletion import DeletionOut, DeletionPreviewOut, expected_text, is_confirmed
from app.shared.enums import RequestKind, ResourceType, StorageState
from app.shared.models.projects import Project
from app.shared.models.shares import ResourceShare
from app.shared.models.storages import Storage
from app.shared.policies.access import ResourceView, authorize


def _out(storage: Storage, project_id: str) -> StorageOut:
    item = StorageOut.model_validate(storage)
    return item.model_copy(update={"shared": storage.origin_project_id != project_id})


def _project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


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
    body: StorageCreateRequestIn,
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
    body: StorageUpdateRequestIn,
) -> RequestOut:
    """F9 : depose une demande de modification de la taille."""
    _project(db, project_id)
    storage = _load(db, storage_id)
    _visible_or_404(db, storage, project_id)
    if storage.size_gb == body.size_gb:
        raise AppError(ErrorCode.BAD_REQUEST, "La taille demandee est identique a la taille actuelle.")
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
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    params: PageParams,
    *,
    state: StorageState | None = None,
    shared: bool | None = None,
    ip_address: str | None = None,
    name: str | None = None,
) -> Page[StorageOut]:
    """F10 : liste les stockages du projet, y compris ceux qui y sont partages."""
    _project(db, project_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right="storage.view",
    )
    shared_ids = select(ResourceShare.resource_id).where(
        ResourceShare.resource_type == ResourceType.STORAGE.value,
        ResourceShare.dest_project_id == project_id,
        ResourceShare.status == "active",
    )
    if shared is True:
        statement = select(Storage).where(Storage.id.in_(shared_ids))
    elif shared is False:
        statement = select(Storage).where(Storage.origin_project_id == project_id)
    else:
        statement = select(Storage).where(
            or_(Storage.origin_project_id == project_id, Storage.id.in_(shared_ids))
        )
    if state is not None:
        statement = statement.where(Storage.state == state.value)
    if ip_address is not None:
        statement = statement.where(Storage.ip_address == ip_address)
    if name:
        statement = statement.where(Storage.name.ilike(f"{name}%"))
    rows, total = paginate(db, statement.order_by(Storage.name, Storage.id), params)
    return Page.build([_out(row, project_id) for row in rows], total, params)


async def get_storage(
    db: Session, iam: IamPort, identity: Identity, project_id: str, storage_id: str
) -> StorageOut:
    """F10 : consulte un stockage visible dans le projet."""
    _project(db, project_id)
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


async def delete_storage_infrastructure(
    db: Session,
    port: StoragePort,
    *,
    actor_id: str,
    storage: Storage,
) -> None:
    """Effets externes et suppression locale d'un stockage. N'enregistre pas la transaction."""
    await revoke_all_for_resource(
        db,
        None,  # un stockage n'est jamais en reseau
        actor_id=actor_id,
        resource_type=ResourceType.STORAGE.value,
        resource_id=storage.id,
    )
    await port.delete_storage(StorageRef(storage.id))
    record_audit(
        db,
        actor_id=actor_id,
        action="storage.deleted",
        entity_type="storage",
        entity_id=storage.id,
    )
    db.delete(storage)


async def delete_storage(
    db: Session,
    iam: IamPort,
    port: StoragePort,
    identity: Identity,
    project_id: str,
    storage_id: str,
    confirmation_text: str | None,
) -> DeletionPreviewOut | DeletionOut:
    """F11 : protocole de suppression en deux temps ; les donnees sont perdues."""
    _project(db, project_id)
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
    text = expected_text(row.name)
    if not is_confirmed(confirmation_text, text):
        active = db.scalar(
            select(ResourceShare.id).where(
                ResourceShare.resource_type == ResourceType.STORAGE.value,
                ResourceShare.resource_id == row.id,
                ResourceShare.status == "active",
            ).limit(1)
        )
        warning = (
            f"Le stockage {row.name} et toutes ses donnees seront definitivement supprimes, "
            "meme s'il est non vide. "
            + ("Ses partages actifs seront revoques. " if active is not None else "")
            + "Cette action est irreversible."
        )
        return DeletionPreviewOut(confirmation_text=text, warning=warning)
    try:
        await revoke_all_for_resource(
            db,
            None,
            actor_id=identity.user_id,
            resource_type=ResourceType.STORAGE.value,
            resource_id=row.id,
        )
        await port.delete_storage(StorageRef(row.id))
    except AppError:
        db.rollback()
        raise
    except (StorageUnavailable, KeyError):
        db.rollback()
        raise upstream_unavailable("Stockage") from None
    record_audit(
        db,
        actor_id=identity.user_id,
        action="storage.deleted",
        entity_type="storage",
        entity_id=row.id,
    )
    db.delete(row)
    db.commit()
    return DeletionOut(
        resource_type="storage",
        resource_id=storage_id,
        message=f"Le stockage {row.name} a bien ete supprime.",
    )
