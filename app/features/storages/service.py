"""Services stockage. Proprietaire : TABA (port Espaces).

Points d'entree orientes ressource pour F8 a F11 et F14. Ils s'appuient sur le socle partage :
- les demandes (F8, F9) sont deposees par le moteur app/features/requests, qui les traite
  ensuite (F15 annulation, F16 decision administrateur, appel du port Stockage) ;
- le partage (F14) est cree par le moteur app/features/shares, qui porte R15 a R20 ;
- le controle d'acces suit la figure 3 (app/shared/policies) a chaque appel.
La consultation ne lit que la base : elle reste possible si le groupe Stockage est indisponible.
"""

import asyncio

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.application.ports.iam import IamPort, Identity
from app.application.ports.storage import StorageError, StoragePort, StorageRef
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import PageParams, paginate
from app.features.requests import service as requests_service
from app.features.shares import service as shares_service
from app.features.storages.schemas import StorageRequestCreateIn, StorageRequestUpdateIn
from app.shared.enums import RequestKind, RequestStatus, ResourceType, ShareStatus, StorageState
from app.shared.models.projects import Project
from app.shared.models.requests import ResourceRequest
from app.shared.models.shares import ResourceShare
from app.shared.models.storages import Storage
from app.shared.policies.access import ResourceView, authorize

# Delai maximal d'un appel direct au groupe Stockage (exigence : appels bornes dans le temps).
STORAGE_CALL_TIMEOUT_SECONDS = 10.0

VIEW = "storage.view"
REQUEST_UPDATE = "storage.request_update"
DELETE = "storage.delete"


def _require_project(db: Session, project_id: str) -> Project:
    """Renvoie le projet ou leve not_found."""
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


def _require_storage(db: Session, storage_id: str) -> Storage:
    """Renvoie le stockage ou leve not_found."""
    storage = db.get(Storage, storage_id)
    if storage is None:
        raise AppError(ErrorCode.NOT_FOUND, "Stockage introuvable.")
    return storage


def _view(storage: Storage) -> ResourceView:
    """Vue du stockage pour la politique d'acces (visibilite par origine ou partage actif)."""
    return ResourceView(ResourceType.STORAGE.value, storage.id, storage.origin_project_id)


async def _storage_in_project(
    db: Session, iam: IamPort, identity: Identity, project_id: str, storage_id: str, right: str
) -> Storage:
    """Figure 3 sur un stockage vu depuis `project_id` : membre, visible, droit requis."""
    _require_project(db, project_id)
    storage = _require_storage(db, storage_id)
    await authorize(
        iam=iam,
        db=db,
        user_id=identity.user_id,
        project_id=project_id,
        required_right=right,
        resource=_view(storage),
    )
    return storage


def _shared_into(project_id: str):
    """Condition SQL : un partage actif rend le stockage visible dans `project_id`."""
    return exists().where(
        ResourceShare.resource_type == ResourceType.STORAGE.value,
        ResourceShare.resource_id == Storage.id,
        ResourceShare.dest_project_id == project_id,
        ResourceShare.status == ShareStatus.ACTIVE.value,
    )


# ---- F8 ----
async def request_create_storage(
    db: Session, iam: IamPort, identity: Identity, project_id: str, body: StorageRequestCreateIn
) -> ResourceRequest:
    """F8 : depose une demande de creation (nom, taille) liee au projet (R1).

    Droit storage.request_create, ou proprietaire. La demande reste en attente jusqu'a la
    decision d'un administrateur ; si elle est acceptee, le projet devient projet d'origine.
    """
    return await requests_service.submit_request(
        db,
        iam,
        author_id=identity.user_id,
        project_id=project_id,
        kind=RequestKind.STORAGE_CREATE,
        payload=body.model_dump(),
        target_resource_id=None,
    )


# ---- F10 ----
async def list_storages(
    db: Session, iam: IamPort, identity: Identity, project_id: str, params: PageParams
) -> tuple[list[Storage], int]:
    """F10 : stockages visibles dans le projet, d'origine ou partages vers lui, pagines."""
    _require_project(db, project_id)
    await authorize(
        iam=iam, db=db, user_id=identity.user_id, project_id=project_id, required_right=VIEW
    )
    statement = (
        select(Storage)
        .where(or_(Storage.origin_project_id == project_id, _shared_into(project_id)))
        .order_by(Storage.name, Storage.id)
    )
    rows, total = paginate(db, statement, params)
    return list(rows), total


async def get_storage(
    db: Session, iam: IamPort, identity: Identity, project_id: str, storage_id: str
) -> Storage:
    """F10 : un stockage visible dans le projet, avec le droit storage.view dans ce projet."""
    return await _storage_in_project(db, iam, identity, project_id, storage_id, VIEW)


# ---- F9 ----
async def request_update_storage(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    storage_id: str,
    body: StorageRequestUpdateIn,
) -> ResourceRequest:
    """F9 : depose une demande de nouvelle taille. Seule la taille est modifiable.

    Refuse un stockage en cours de suppression, une taille identique a l'actuelle, et une
    seconde demande de modification tant qu'une premiere est en attente sur ce stockage.
    Sur un stockage partage, ce sont les droits du projet `project_id` qui s'appliquent (R12).
    """
    storage = await _storage_in_project(db, iam, identity, project_id, storage_id, REQUEST_UPDATE)
    if storage.state == StorageState.DELETING.value:
        raise AppError(ErrorCode.INVALID_STATE, "Le stockage est en cours de suppression.")
    if body.size == storage.size:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            f"La taille demandee est identique a la taille actuelle ({storage.size} Go).",
        )
    pending = db.scalar(
        select(ResourceRequest.id).where(
            ResourceRequest.kind == RequestKind.STORAGE_UPDATE.value,
            ResourceRequest.target_resource_id == storage.id,
            ResourceRequest.status == RequestStatus.PENDING.value,
        )
    )
    if pending is not None:
        raise AppError(
            ErrorCode.CONFLICT,
            "Une demande de modification est deja en attente pour ce stockage.",
            details={"request_id": pending},
        )
    return await requests_service.submit_request(
        db,
        iam,
        author_id=identity.user_id,
        project_id=project_id,
        kind=RequestKind.STORAGE_UPDATE,
        payload=body.model_dump(),
        target_resource_id=storage.id,
    )


# ---- F11 ----
def deletion_warning(storage: Storage, active_shares: int) -> str:
    """Texte de l'avertissement affiche avant toute suppression (R6)."""
    shares = f" et ses {active_shares} partage(s) actif(s) seront revoques" if active_shares else ""
    return (
        f"Attention : la suppression du stockage \"{storage.name}\" ({storage.size} Go) est "
        f"definitive. Les donnees qu'il contient seront perdues{shares}. "
        "Renvoyez la requete avec {\"confirm\": true} pour confirmer."
    )


def _active_shares(db: Session, storage_id: str) -> list[ResourceShare]:
    """Partages actifs du stockage."""
    return list(
        db.scalars(
            select(ResourceShare).where(
                ResourceShare.resource_type == ResourceType.STORAGE.value,
                ResourceShare.resource_id == storage_id,
                ResourceShare.status == ShareStatus.ACTIVE.value,
            )
        )
    )


async def delete_storage(
    db: Session,
    iam: IamPort,
    storage_port: StoragePort,
    identity: Identity,
    project_id: str,
    storage_id: str,
    confirm: bool,
) -> None:
    """F11 : suppression directe, sans demande ni administrateur, meme avec des donnees (R6).

    Sans confirmation : bad_request avec l'avertissement, rien n'est touche.
    Avec confirmation : le stockage passe en `deleting`, le groupe Stockage est appele (avec un
    delai maximal), puis ses partages sont revoques et la ligne est retiree, en une transaction.
    Si le groupe Stockage echoue, l'etat precedent est restaure : rien n'est applique a moitie.
    Un stockage reste en `deleting` apres une interruption peut etre supprime a nouveau,
    l'appel au port etant rejouable.
    """
    storage = await _storage_in_project(db, iam, identity, project_id, storage_id, DELETE)
    shares = _active_shares(db, storage.id)
    if not confirm:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            deletion_warning(storage, len(shares)),
            details={"confirm_required": True},
        )

    previous_state = storage.state
    storage.state = StorageState.DELETING.value  # bloque partages et demandes pendant l'appel
    db.commit()
    try:
        await asyncio.wait_for(
            storage_port.delete_storage(StorageRef(storage.id)), STORAGE_CALL_TIMEOUT_SECONDS
        )
    except (StorageError, TimeoutError):
        storage.state = previous_state
        db.commit()
        raise upstream_unavailable("Stockage") from None

    for share in shares:
        share.status = ShareStatus.REVOKED.value
    record_audit(
        db,
        actor_id=identity.user_id,
        action="storage.deleted",
        entity_type="storage",
        entity_id=storage.id,
        data={
            "name": storage.name,
            "size": storage.size,
            "project_id": project_id,
            "origin_project_id": storage.origin_project_id,
            "revoked_shares": [share.id for share in shares],
        },
    )
    db.delete(storage)
    db.commit()


# ---- F14 ----
async def share_storage(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    storage_id: str,
    dest_project_id: str,
) -> ResourceShare:
    """F14 : partage le stockage depuis son projet d'origine vers un projet du meme proprietaire.

    Le moteur de partages verifie le reste : meme proprietaire (R15), droit storage.share dans
    l'origine et appartenance au destinataire (R18), pas de doublon actif, pas de suppression en
    cours. Activation immediate, sans administrateur (R20) et sans appel au groupe Stockage.
    """
    _require_project(db, project_id)
    storage = _require_storage(db, storage_id)
    if storage.origin_project_id != project_id:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            "Un stockage se partage depuis son projet d'origine.",
            details={"origin_project_id": storage.origin_project_id},
        )
    return await shares_service.create_share(
        db,
        iam,
        user_id=identity.user_id,
        resource_type=ResourceType.STORAGE,
        resource_id=storage.id,
        dest_project_id=dest_project_id,
    )


async def list_storage_shares(
    db: Session,
    iam: IamPort,
    identity: Identity,
    project_id: str,
    storage_id: str,
    params: PageParams,
    status: ShareStatus | None = None,
) -> tuple[list[ResourceShare], int]:
    """Partages d'un stockage visible dans le projet, pagines, filtrables par statut.

    Le retrait se fait par le moteur partage : POST /api/v1/shares/{share_id}/revoke.
    """
    storage = await _storage_in_project(db, iam, identity, project_id, storage_id, VIEW)
    statement = select(ResourceShare).where(
        ResourceShare.resource_type == ResourceType.STORAGE.value,
        ResourceShare.resource_id == storage.id,
    )
    if status is not None:
        statement = statement.where(ResourceShare.status == status.value)
    rows, total = paginate(
        db, statement.order_by(ResourceShare.created_at.desc(), ResourceShare.id.desc()), params
    )
    return list(rows), total
