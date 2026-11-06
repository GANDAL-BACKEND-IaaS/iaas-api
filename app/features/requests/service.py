"""Moteur des demandes : depot, annulation, decision et mise a jour liee aux packs.

Regles portees ici : R1, R2, R3, R4, R5, R13, R14, F15, F16.
Les handlers techniques sont injectes par kind et ne doivent pas committer eux-memes.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.application.ports.decision import DecisionPort
from app.application.ports.hypervisor import HypervisorPort, HypervisorUnavailable, VmRef, VmSpec
from app.application.ports.iam import GlobalRole, IamPort
from app.application.ports.notifications import Notification, NotificationsPort
from app.core.audit import record_audit
from app.core.errors import AppError, ErrorCode, upstream_unavailable
from app.core.pagination import PageParams, paginate
from app.features.requests.schemas import (
    VMCreateRequestIn,
    VMUpdateRequestIn,
)
from app.shared.enums import RequestKind, RequestStatus, ResourceType, VmState
from app.shared.models.base import new_id
from app.shared.models.packs import Pack
from app.shared.models.projects import Project
from app.shared.models.requests import ResourceRequest
from app.shared.models.vms import Vm
from app.shared.policies.access import ResourceView, authorize
from app.shared.time import utcnow

logger = logging.getLogger(__name__)

_RIGHT_FOR_KIND = {
    RequestKind.VM_CREATE: "vm.request_create",
    RequestKind.VM_UPDATE: "vm.request_update",
}

Handler = Callable[["RequestContext"], Awaitable[None]]
_HANDLERS: dict[str, Handler] = {}


@dataclass
class RequestContext:
    """Contexte passe a un handler : demande, session et ports techniques."""

    db: Session
    request: ResourceRequest
    hypervisor: HypervisorPort


def register_handler(kind: RequestKind, handler: Handler) -> None:
    """Associe le traitement technique d'un kind de demande."""
    _HANDLERS[kind.value] = handler


def clear_handlers() -> None:
    """Retire tous les handlers. Utile aux tests."""
    _HANDLERS.clear()


def _validation(exc: ValidationError) -> AppError:
    return AppError(ErrorCode.VALIDATION_ERROR, "Charge utile invalide.", details=exc.errors())


def _get_request(db: Session, request_id: str) -> ResourceRequest:
    row = db.get(ResourceRequest, request_id)
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "Demande introuvable.")
    return row


def _require_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, "Projet introuvable.")
    return project


def _normalize_vm_create(db: Session, payload: dict) -> dict:
    try:
        data = VMCreateRequestIn.model_validate(payload)
    except ValidationError as exc:
        raise _validation(exc) from None
    if data.pack_id is not None:
        pack = db.get(Pack, data.pack_id)
        if pack is None:
            raise AppError(ErrorCode.NOT_FOUND, "Pack introuvable.")
        return {
            "name": data.name,
            "pack_id": pack.id,
            "ram_gb": pack.ram_gb,
            "vcpu": pack.vcpu,
            "vram_gb": pack.vram_gb,
            "ssd_gb": pack.ssd_gb,
        }
    assert data.configuration is not None  # garanti par le validateur du schema
    return {"name": data.name, "configuration": data.configuration.model_dump()}


def _normalize_vm_update(payload: dict) -> dict:
    try:
        return VMUpdateRequestIn.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise _validation(exc) from None


def _prepare(
    db: Session,
    kind: RequestKind,
    payload: dict,
    target_resource_id: str | None,
) -> tuple[dict, str | None, ResourceView | None]:
    """Valide la charge et retourne (payload normalise, type cible, vue ressource)."""
    if kind == RequestKind.VM_CREATE:
        if target_resource_id is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Une creation ne cible pas une ressource existante.")
        return _normalize_vm_create(db, payload), None, None
    if target_resource_id is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, "La modification exige target_resource_id.")
    vm = db.get(Vm, target_resource_id)
    if vm is None:
        raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")
    if vm.state == VmState.DELETING.value:
        raise AppError(ErrorCode.INVALID_STATE, "La VM est en cours de suppression.")
    view = ResourceView(ResourceType.VM.value, vm.id, vm.origin_project_id)
    return _normalize_vm_update(payload), ResourceType.VM.value, view


def _find_duplicate(
    db: Session,
    *,
    kind: RequestKind,
    project_id: str,
    target_resource_id: str,
    payload: dict,
) -> ResourceRequest | None:
    statement = select(ResourceRequest).where(
        ResourceRequest.kind == kind.value,
        ResourceRequest.status == RequestStatus.PENDING.value,
        ResourceRequest.project_id == project_id,
        ResourceRequest.target_resource_id == target_resource_id,
    )
    return next((row for row in db.scalars(statement) if row.payload == payload), None)


async def submit_request(
    db: Session,
    iam: IamPort,
    *,
    author_id: str,
    project_id: str,
    kind: RequestKind,
    payload: dict,
    target_resource_id: str | None,
    # INJECTE, par mot-cle et avec un defaut : les appels positionnels
    # existants — leurs tests compris — continuent de marcher a
    # l identique, et « None » garde le comportement d avant.
    decision: DecisionPort | None = None,
) -> ResourceRequest:
    """Enregistre une demande en attente apres controle des droits (R1, R2, R13)."""
    _require_project(db, project_id)
    normalized, target_type, view = _prepare(db, kind, payload, target_resource_id)
    await authorize(
        decision=decision,
        iam=iam,
        db=db,
        user_id=author_id,
        project_id=project_id,
        required_right=_RIGHT_FOR_KIND[kind],
        resource=view,
    )
    if target_resource_id is not None:
        duplicate = _find_duplicate(
            db,
            kind=kind,
            project_id=project_id,
            target_resource_id=target_resource_id,
            payload=normalized,
        )
        if duplicate is not None:
            raise AppError(
                ErrorCode.CONFLICT,
                "Une demande identique est deja en attente.",
                details={"request_id": duplicate.id},
            )
    row = ResourceRequest(
        project_id=project_id,
        author_id=author_id,
        kind=kind.value,
        status=RequestStatus.PENDING.value,
        payload=normalized,
        target_resource_type=target_type,
        target_resource_id=target_resource_id,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor_id=author_id,
        action="request.submitted",
        entity_type="request",
        entity_id=row.id,
        data={"kind": kind.value, "project_id": project_id},
    )
    db.commit()
    db.refresh(row)
    return row


def cancel_request(db: Session, *, author_id: str, request_id: str) -> ResourceRequest:
    """Annule une demande en attente. Seul l'auteur peut le faire (R5, F15)."""
    row = _get_request(db, request_id)
    if row.author_id != author_id:
        raise AppError(ErrorCode.FORBIDDEN, "Seul l'auteur peut annuler la demande.")
    if row.status != RequestStatus.PENDING.value:
        raise AppError(ErrorCode.INVALID_STATE, "Seule une demande en attente peut etre annulee.")
    row.status = RequestStatus.CANCELLED.value
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=author_id,
        action="request.cancelled",
        entity_type="request",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return row


async def _notify(notifications: NotificationsPort, user_id: str, subject: str, message: str) -> None:
    """Notifie sans faire echouer la decision deja enregistree."""
    try:
        await notifications.notify(Notification(user_id=user_id, subject=subject, message=message))
    except Exception:
        logger.warning("Notification non delivree pour %s.", user_id)


def _require_admin(role: GlobalRole) -> None:
    if role != GlobalRole.ADMIN:
        raise AppError(ErrorCode.FORBIDDEN, "Reserve aux administrateurs.")


def _require_pending(row: ResourceRequest) -> None:
    if row.status != RequestStatus.PENDING.value:
        raise AppError(ErrorCode.INVALID_STATE, "Seule une demande en attente peut etre traitee.")


def _tailles(payload: dict) -> dict[str, int]:
    """La taille demandee, quelle que soit la forme du payload normalise.

    « _normalize_vm_create » rend soit `{"configuration": {...}}` (configuration
    explicite), soit les champs A PLAT (resolus depuis un pack). Les deux sont
    lues ici, parce qu une seule des deux formes donnerait un quota nul sur la
    moitie des demandes — et un quota nul ne refuse rien, il compte faux.
    """
    source = payload.get("configuration") or payload
    return {cle: int(source.get(cle, 0) or 0)
            for cle in ("ram_gb", "vcpu", "vram_gb", "ssd_gb")}


def _ressources_de_quota(payload: dict) -> dict[str, int]:
    return {cle: quantite for cle, quantite in _quantites_de_quota(payload).items()
            if quantite}


def _quantites_de_quota(payload: dict) -> dict[str, int]:
    t = _tailles(payload)
    return {
        "vm_count": 1,
        "vcpu": t["vcpu"],
        "ram_gb": t["ram_gb"],
        "disk_gb": t["ssd_gb"],
        # IAM exprime la VRAM en Mio; garder le zero permet aussi de la rendre
        # explicitement lors d'un redimensionnement vers une VM sans GPU.
        "gpu_mem_mb": t["vram_gb"] * 1024,
    }


def _quantites_vm(vm: Vm) -> dict[str, int]:
    return {
        "vm_count": 1,
        "vcpu": vm.vcpu,
        "ram_gb": vm.ram_gb,
        "disk_gb": vm.ssd_gb,
        "gpu_mem_mb": vm.vram_gb * 1024,
    }


async def _compenser_creation_vm(
    context: RequestContext,
    decision: DecisionPort,
    *,
    rendre_quota: bool,
) -> None:
    vm_id = context.request.target_resource_id
    if vm_id is None:
        return
    try:
        await context.hypervisor.delete_vm(VmRef(vm_id))
        if rendre_quota:
            await decision.rendre(sujet=context.request.author_id, id_ressource=vm_id)
    except Exception as exc:
        logger.exception(
            "Impossible de compenser la creation de la VM %s pour la demande %s",
            vm_id,
            context.request.id,
        )
        raise upstream_unavailable("compensation de VM") from exc


async def creer_en_libre_service(
    db: Session,
    iam: IamPort,
    *,
    author_id: str,
    project_id: str,
    payload: dict,
    hypervisor: HypervisorPort,
    notifications: NotificationsPort,
    decision: DecisionPort | None = None,
) -> ResourceRequest:
    """Crée une VM SANS acceptation par un administrateur (R1, R2, R13).

    POURQUOI CE CHEMIN EXISTE, ET POURQUOI IL REMPLACE L AUTRE POUR LES VM.
    Faire valider chaque VM par un administrateur avait un sens quand rien ne
    savait dire si l auteur y avait droit. IAM le sait : l administrateur a
    valide le COMPTE et pose les QUOTAS, et c est tout ce qu il a a decider.
    Lui redemander son avis a chaque machine, c est lui faire relire un calcul
    que le service de decision vient de faire — et c est aussi la file
    d attente ou un etudiant perd deux jours pour une VM de 2 vCPU.

    LE QUOTA EST LA SEULE AUTORITE ICI. Si IAM accorde, la VM se cree. S il
    refuse, le motif remonte tel quel : « il vous reste 0 vCPU sur 4 », et non
    « demande en attente ».

    CE QUI PASSE ENCORE PAR UNE DEMANDE : tout ce qui depasse le quota ou le
    catalogue des profils. Une taille hors profil, un quota a relever, un GPU
    de plus — la demande reste le bon endroit pour une EXCEPTION. Elle n est
    plus le chemin normal.

    LA TRACE N EST PAS PERDUE. Une ligne de demande est quand meme ecrite, deja
    acceptee, avec « libre-service » en note : l audit et l historique voient
    exactement ce qu ils voyaient avant, et « GET /requests » continue de rendre
    la liste complete de ce qui a ete cree.
    """
    _require_project(db, project_id)
    normalized, target_type, view = _prepare(
        db, RequestKind.VM_CREATE, payload, None)
    # LA DECISION D ABORD, AVANT D ECRIRE QUOI QUE CE SOIT. Ecrire la ligne
    # puis demander ferait rester une demande orpheline a chaque refus.
    await authorize(
        decision=decision,
        iam=iam,
        db=db,
        user_id=author_id,
        project_id=project_id,
        required_right=_RIGHT_FOR_KIND[RequestKind.VM_CREATE],
        resource=view,
    )
    row = ResourceRequest(
        id=new_id(),
        project_id=project_id,
        author_id=author_id,
        kind=RequestKind.VM_CREATE.value,
        payload=normalized,
        target_resource_type=target_type,
        target_resource_id=None,
        status=RequestStatus.PENDING.value,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(row)
    db.flush()

    handler = _HANDLERS.get(row.kind)
    if handler is None:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"Aucun traitement technique n'est enregistre pour {row.kind}.",
        )
    context = RequestContext(db=db, request=row, hypervisor=hypervisor)
    # EXACTEMENT LE MEME CHEMIN QUE L ACCEPTATION : decision au nom de
    # l auteur, quota retenu, handler, confirmation APRES l hyperviseur.
    await _executer(db, row, context, handler, row.id, decision=decision)

    row.status = RequestStatus.ACCEPTED.value
    row.admin_note = "libre-service"
    row.decided_at = utcnow()
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=author_id,
        action="vm.created_self_service",
        entity_type="request",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return row


async def _executer(
    db: Session,
    row: ResourceRequest,
    context: RequestContext,
    handler: Handler,
    request_id: str,
    *,
    decision: DecisionPort | None,
) -> None:
    """Décide, retient le quota, lance le handler, confirme. Dans cet ordre.

    EXTRAIT DE « accept_request » LE 5 NOVEMBRE 2026, pour que le LIBRE-SERVICE
    passe exactement par ici. Recopier ces cent lignes dans un second chemin
    les aurait fait diverger — et le jour de la divergence, l un des deux
    compterait faux sans que personne ne le voie.
    """
    # ─── LE QUOTA EST RETENU ICI, ET NULLE PART AILLEURS ────────────────────
    #
    # C est le moment ou la ressource vient a l existence. Le retenir au DEPOT de
    # la demande le bloquerait pendant les jours ou elle attend un administrateur,
    # et dix demandes en attente epuiseraient un quota sans qu aucune VM
    # n existe. On decide tot (dans `submit_request`, par `authorize`) et on
    # compte tard.
    #
    # LA DECISION EST REDEMANDEE, au nom de l AUTEUR : entre le depot et
    # maintenant, son role a pu expirer, son projet etre archive, une politique
    # changer. Accepter sur la foi d une decision de trois jours applique un
    # droit perime.
    if decision is not None and row.kind == RequestKind.VM_CREATE.value:
        await decision.autoriser(
            sujet=row.author_id, action="vm:create",
            ressource={"type": "vm", "id": str(row.payload.get("name") or row.id),
                       "projet": row.project_id},
            contexte={"vcpu": _tailles(row.payload)["vcpu"],
                      "ram_gb": _tailles(row.payload)["ram_gb"],
                      "disk_gb": _tailles(row.payload)["ssd_gb"]})
        async with decision.transaction(
                sujet=row.author_id, projet=row.project_id,
                ressources=_ressources_de_quota(row.payload)) as jeton:
            try:
                await handler(context)
            except AppError:
                try:
                    await _compenser_creation_vm(context, decision, rendre_quota=False)
                finally:
                    db.rollback()
                raise
            except HypervisorUnavailable:
                try:
                    await _compenser_creation_vm(context, decision, rendre_quota=False)
                finally:
                    db.rollback()
                raise upstream_unavailable("infrastructure") from None
            except Exception as exc:
                try:
                    await _compenser_creation_vm(context, decision, rendre_quota=False)
                finally:
                    db.rollback()
                logger.exception("Echec du traitement de la demande %s", request_id)
                raise upstream_unavailable("infrastructure") from exc
            # CONFIRMER APRES le traitement : confirmer d abord compterait une VM
            # qu un echec de l hyperviseur laisserait inexistante. Et si le corps
            # leve, la sortie du bloc LIBERE la reservation.
            vm_id = str(row.target_resource_id or row.id)
            try:
                await decision.confirmer(jeton, id_ressource=vm_id, type_ressource="vm")
            except Exception:
                try:
                    await _compenser_creation_vm(context, decision, rendre_quota=True)
                finally:
                    db.rollback()
                raise
    elif decision is not None and row.kind == RequestKind.VM_UPDATE.value:
        await decision.autoriser(
            sujet=row.author_id, action="vm:update",
            ressource={"type": "vm", "id": str(row.target_resource_id),
                       "projet": row.project_id},
            contexte={"vcpu": _tailles(row.payload)["vcpu"],
                      "ram_gb": _tailles(row.payload)["ram_gb"],
                      "disk_gb": _tailles(row.payload)["ssd_gb"]})
        vm = db.get(Vm, row.target_resource_id)
        if vm is None:
            raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")
        anciennes_quantites = _quantites_vm(vm)
        anciennes_tailles = VmSpec(
            vm.name, vm.ram_gb, vm.vcpu, vm.vram_gb, vm.ssd_gb
        )
        await decision.redimensionner(
            sujet=row.author_id, id_ressource=str(row.target_resource_id),
            quantites=_quantites_de_quota(row.payload))
        try:
            await handler(context)
        except Exception as operation_error:
            db.rollback()
            try:
                await context.hypervisor.update_vm(
                    VmRef(str(row.target_resource_id)), anciennes_tailles
                )
            except Exception as compensation_error:
                logger.exception(
                    "Impossible de restaurer la VM %s apres l'echec de sa modification",
                    row.target_resource_id,
                )
                raise upstream_unavailable("compensation de VM") from compensation_error
            try:
                await decision.redimensionner(
                    sujet=row.author_id,
                    id_ressource=str(row.target_resource_id),
                    quantites=anciennes_quantites,
                )
            except Exception as compensation_error:
                logger.exception(
                    "Impossible de restaurer le quota de la VM %s",
                    row.target_resource_id,
                )
                raise upstream_unavailable("restauration du quota") from compensation_error
            if isinstance(operation_error, AppError):
                raise
            logger.exception("Echec du traitement de la demande %s", request_id)
            raise upstream_unavailable("infrastructure") from operation_error
    else:
        # AUCUN service de decision branche : exactement le chemin d avant la
        # greffe, traitement d erreur compris.
        try:
            await handler(context)
        except AppError:
            db.rollback()
            raise
        except HypervisorUnavailable:
            db.rollback()
            raise upstream_unavailable("infrastructure") from None
        except Exception:
            db.rollback()
            logger.exception("Echec du traitement de la demande %s", request_id)
            raise upstream_unavailable("infrastructure") from None



async def accept_request(
    db: Session,
    *,
    actor_id: str,
    actor_role: GlobalRole,
    request_id: str,
    note: str | None,
    hypervisor: HypervisorPort,
    notifications: NotificationsPort,
    # INJECTE, par mot-cle et avec un defaut : les appels positionnels
    # existants — leurs tests compris — continuent de marcher a
    # l identique, et « None » garde le comportement d avant.
    decision: DecisionPort | None = None,
) -> ResourceRequest:
    """Accepte une demande sans la modifier, puis appelle le handler du kind (R3, F16)."""
    _require_admin(actor_role)
    row = _get_request(db, request_id)
    _require_pending(row)
    handler = _HANDLERS.get(row.kind)
    if handler is None:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            f"Aucun traitement technique n'est enregistre pour {row.kind}.",
        )
    context = RequestContext(db=db, request=row, hypervisor=hypervisor)

    await _executer(db, row, context, handler, request_id,
                    decision=decision)
    row.status = RequestStatus.ACCEPTED.value
    row.admin_note = note
    row.decided_at = utcnow()
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=actor_id,
        action="request.accepted",
        entity_type="request",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    await _notify(
        notifications,
        row.author_id,
        "Demande acceptee",
        f"La demande {row.id} a ete acceptee.",
    )
    return row


async def refuse_request(
    db: Session,
    *,
    actor_id: str,
    actor_role: GlobalRole,
    request_id: str,
    note: str | None,
    notifications: NotificationsPort,
) -> ResourceRequest:
    """Refuse une demande sans la modifier. La remarque reste optionnelle (R3, R4, F16)."""
    _require_admin(actor_role)
    row = _get_request(db, request_id)
    _require_pending(row)
    row.status = RequestStatus.REFUSED.value
    row.admin_note = note
    row.decided_at = utcnow()
    row.updated_at = utcnow()
    record_audit(
        db,
        actor_id=actor_id,
        action="request.refused",
        entity_type="request",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    await _notify(
        notifications,
        row.author_id,
        "Demande refusee",
        f"La demande {row.id} a ete refusee.",
    )
    return row


async def get_request(
    db: Session, iam: IamPort, *, actor_id: str, actor_role: GlobalRole, request_id: str
) -> ResourceRequest:
    """Retourne une demande visible par son auteur, un membre du projet ou un administrateur."""
    row = _get_request(db, request_id)
    if actor_role == GlobalRole.ADMIN or row.author_id == actor_id:
        return row
    if row.project_id not in await iam.list_projects(actor_id):
        raise AppError(ErrorCode.FORBIDDEN, "Cette demande ne vous est pas accessible.")
    return row


async def list_requests(
    db: Session,
    iam: IamPort,
    *,
    actor_id: str,
    actor_role: GlobalRole,
    params: PageParams,
    status: RequestStatus | None = None,
    kind: RequestKind | None = None,
    project_id: str | None = None,
    author_id: str | None = None,
) -> tuple[list[ResourceRequest], int]:
    """Liste paginee. Un administrateur voit tout, un utilisateur voit ses demandes et ses projets."""
    is_admin = actor_role == GlobalRole.ADMIN
    if author_id is not None and not is_admin:
        raise AppError(ErrorCode.FORBIDDEN, "Le filtre author_id est reserve aux administrateurs.")
    member_ids: set[str] = set() if is_admin else set(await iam.list_projects(actor_id))
    if project_id is not None:
        _require_project(db, project_id)
        if not is_admin and project_id not in member_ids:
            raise AppError(ErrorCode.FORBIDDEN, "Ce projet est hors de votre perimetre.")
    statement = select(ResourceRequest)
    if not is_admin:
        statement = statement.where(
            or_(
                ResourceRequest.author_id == actor_id,
                ResourceRequest.project_id.in_(member_ids or {"-"}),
            )
        )
    if project_id is not None:
        statement = statement.where(ResourceRequest.project_id == project_id)
    if author_id is not None:
        statement = statement.where(ResourceRequest.author_id == author_id)
    if status is not None:
        statement = statement.where(ResourceRequest.status == status.value)
    if kind is not None:
        statement = statement.where(ResourceRequest.kind == kind.value)
    statement = statement.order_by(ResourceRequest.created_at.desc(), ResourceRequest.id.desc())
    rows, total = paginate(db, statement, params)
    return list(rows), total


def _vm_spec_from_payload(name: str, payload: dict) -> VmSpec:
    config = payload.get("configuration") or payload
    return VmSpec(
        name=name,
        ram_gb=config["ram_gb"],
        vcpu=config["vcpu"],
        vram_gb=config["vram_gb"],
        ssd_gb=config["ssd_gb"],
    )


def _spec_configuration(payload: dict) -> dict:
    return dict(payload.get("configuration") or payload)


async def refresh_pending_vm_creates(
    db: Session,
    *,
    actor_id: str,
    pack: Pack,
    notifications: NotificationsPort,
) -> list[ResourceRequest]:
    """Met a jour les demandes de creation en attente qui reposent sur ce pack (R14).

    Elles restent en attente : l'administrateur doit les valider a nouveau.
    Les VM deja creees ne sont pas modifiees.
    """
    statement = select(ResourceRequest).where(
        ResourceRequest.kind == RequestKind.VM_CREATE.value,
        ResourceRequest.status == RequestStatus.PENDING.value,
    )
    configuration = {
        "ram_gb": pack.ram_gb,
        "vcpu": pack.vcpu,
        "vram_gb": pack.vram_gb,
        "ssd_gb": pack.ssd_gb,
    }
    touched: list[ResourceRequest] = []
    for row in db.scalars(statement):
        if row.payload.get("pack_id") != pack.id:
            continue
        updated = dict(row.payload)
        if "configuration" in updated:
            updated["configuration"] = configuration
        else:
            updated.update(configuration)
        row.payload = updated
        row.updated_at = utcnow()
        record_audit(
            db,
            actor_id=actor_id,
            action="request.pack_refreshed",
            entity_type="request",
            entity_id=row.id,
            data={"pack_id": pack.id},
        )
        touched.append(row)
    db.commit()
    for row in touched:
        db.refresh(row)
        await _notify(
            notifications,
            row.author_id,
            "Demande mise a jour",
            f"La demande {row.id} a ete mise a jour suite a la modification du pack.",
        )
    return touched


async def handle_vm_create(context: RequestContext) -> None:
    """Cree la VM via l'hyperviseur puis l'enregistre dans le projet de la demande."""
    payload = context.request.payload
    spec = _vm_spec_from_payload(payload["name"], payload)
    try:
        ref = await context.hypervisor.create_vm(spec)
    except HypervisorUnavailable:
        raise upstream_unavailable("Hyperviseur") from None
    context.request.target_resource_type = ResourceType.VM.value
    context.request.target_resource_id = ref.vm_id
    context.db.add(
        Vm(
            id=ref.vm_id,
            origin_project_id=context.request.project_id,
            name=payload["name"],
            ip_address=ref.ip_address,
            ram_gb=spec.ram_gb,
            vcpu=spec.vcpu,
            vram_gb=spec.vram_gb,
            ssd_gb=spec.ssd_gb,
            pack_id=payload.get("pack_id"),
            state=VmState.STOPPED.value,
        )
    )


async def handle_vm_update(context: RequestContext) -> None:
    """Applique la configuration complete demandee, sans en inventer d'autres (R3)."""
    vm = context.db.get(Vm, context.request.target_resource_id)
    if vm is None:
        raise AppError(ErrorCode.NOT_FOUND, "VM introuvable.")
    configuration = _spec_configuration(context.request.payload)
    for field, value in configuration.items():
        setattr(vm, field, value)
    try:
        await context.hypervisor.update_vm(
            VmRef(vm.id),
            VmSpec(vm.name, vm.ram_gb, vm.vcpu, vm.vram_gb, vm.ssd_gb),
        )
    except HypervisorUnavailable:
        raise upstream_unavailable("Hyperviseur") from None


def register_default_handlers() -> None:
    """Enregistre les traitements techniques par defaut, adosses aux ports."""
    register_handler(RequestKind.VM_CREATE, handle_vm_create)
    register_handler(RequestKind.VM_UPDATE, handle_vm_update)
