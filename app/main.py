"""Point d'entree FastAPI du backend IaaS.

Le schema est gere par Alembic. Au demarrage, on insere les donnees de reference puis
on rehydrate le mock IAM depuis la base metier : les projets et les droits survivent
ainsi a un redemarrage du processus.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.router import router as v1_router
from app.application.ports.decision import Refuse, ServiceIndisponible
from app.core.database import SessionLocal, get_db
from app.core.dependencies import get_iam
from app.core.errors import (
    ErrorCode,
    error_responses,
    register_exception_handlers,
    upstream_unavailable,
)
from app.core.settings import get_settings
from app.shared.models import (  # noqa: F401
    audit,
    identities,
    networks,
    packs,
    projects,
    requests,
    rights,
    shares,
    vms,
)
from app.shared.models.projects import Membership, Project
from app.shared.models.rights import RightModel
from app.shared.policies.rights import membership_rights
from app.shared.seed.seeder import seed_default_packs, seed_default_profiles, seed_rights


def rehydrate_iam(db: Session) -> None:
    """Recharge projets, propriete et droits des invites dans le mock IAM."""
    restore = getattr(get_iam(), "restore_project", None)
    if restore is None:
        return
    known = list(db.scalars(select(RightModel.code)))
    for project in db.scalars(select(Project)):
        memberships = list(
            db.scalars(select(Membership).where(Membership.project_id == project.id))
        )
        guests = {
            member.user_id: membership_rights(member, known)
            for member in memberships
            if member.user_id != project.owner_id
        }
        restore(project.id, project.owner_id, guests)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Insere les donnees de reference et rehydrate l'IAM (apres migration)."""
    with SessionLocal() as db:
        seed_rights(db)
        seed_default_profiles(db)
        seed_default_packs(db)
        rehydrate_iam(db)
    yield


app = FastAPI(
    title="IaaS API",
    version="1.0.0",
    summary="Backend metier d'une plateforme IaaS.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
register_exception_handlers(app)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    """Sonde de sante non versionnee, conservee hors du contrat metier."""
    return {"status": "ok"}


class ReadinessOut(BaseModel):
    """Etat de disponibilite de l'application."""

    status: str = Field(examples=["ready"])
    # CE QUI COMPTE LES QUOTAS, OU RIEN. Une sonde qui ne dit que « ready »
    # laisserait une plateforme servir des mois sans qu aucun quota ne soit
    # compte, et personne ne le verrait : rien ne casse, les chiffres mentent.
    # Ici, la supervision le lit.
    decision: str


@app.get(
    "/ready",
    response_model=ReadinessOut,
    operation_id="get_readiness",
    summary="Disponibilite de l'application",
    tags=["sante"],
    responses=error_responses(ErrorCode.UPSTREAM_UNAVAILABLE),
)
def ready(db: Session = Depends(get_db)) -> ReadinessOut:
    """Sonde de disponibilite : verifie les dependances necessaires au service.

    A ce stade, la base de donnees est la seule dependance reelle. Les ports
    hyperviseur, reseau, IAM et notifications sont encore des mocks : les sonder
    n'apporterait aucune information d'exploitation.

    Le champ `decision` rend le reglage du service de decision — « off », « fake »
    ou « gandal ». Il est la pour qu une supervision puisse ALERTER sur « off » :
    un backend qui ne compte aucun quota ne doit pas pouvoir servir des mois sans
    que quiconque s en apercoive.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise upstream_unavailable("base de donnees") from None
    return ReadinessOut(status="ready", decision=get_settings().decision_backend)


app.include_router(v1_router)


# LE SERVICE DE DECISION EST BRANCHE AU DEMARRAGE, une fois. `authorize` le
# retrouve par la — voir le commentaire de `access.py` sur ce compromis.
# ON LE DIT FORT AU DEMARRAGE. Un backend qui ne compte aucun quota doit
# l annoncer, pas le taire : « off » est un etat de transition, pas un reglage.
_reglage = get_settings().decision_backend
if _reglage == "off":
    logging.getLogger("app").warning(
        "DECISION_BACKEND=off : AUCUNE decision IAM n est demandee et AUCUN quota "
        "n est compte. A poser sur « gandal » avant la mise en service.")
elif _reglage == "fake":
    logging.getLogger("app").warning(
        "DECISION_BACKEND=fake : quotas en MEMOIRE, remis a zero a chaque "
        "redemarrage. Developpement seulement.")


@app.exception_handler(Refuse)
async def _refus_de_decision(_: Request, exc: Refuse) -> JSONResponse:
    """Traduit un refus du service de decision en RFC 9457 (`problem+json`).

    Sans ce gestionnaire, un refus de quota sort en 500 et l'utilisateur lit
    « erreur interne » la ou IAM avait ecrit « il vous reste 2 vCPU sur 4 ». Le
    motif voyage aussi : un client doit pouvoir distinguer « reessaie plus tard »
    (503) de « ne reessaie pas » (403).
    """
    return JSONResponse(
        status_code=exc.statut,
        media_type="application/problem+json",
        content={
            "type": f"https://gandal.internal/problemes/{exc.motif or 'refus'}",
            "title": "Service de decision indisponible"
                     if isinstance(exc, ServiceIndisponible) else "Refuse",
            "status": exc.statut,
            "detail": exc.explication or str(exc),
            "motif": exc.motif,
        },
    )
