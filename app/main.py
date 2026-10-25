"""Point d'entree FastAPI du backend IaaS.

Le schema est gere par Alembic. Au demarrage, on insere les donnees de reference puis
on rehydrate le mock IAM depuis la base metier : les projets et les droits survivent
ainsi a un redemarrage du processus.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.router import router as v1_router
from app.core.database import SessionLocal, get_db
from app.core.dependencies import get_iam
from app.core.errors import (
    ErrorCode,
    error_responses,
    register_exception_handlers,
    upstream_unavailable,
)
from app.shared.models import (  # noqa: F401
    audit,
    identities,
    networks,
    packs,
    projects,
    requests,
    rights,
    shares,
    storages,
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
    hyperviseur, stockage, reseau, DNS, IAM et notifications sont encore des
    mocks : les sonder n'apporterait aucune information d'exploitation.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise upstream_unavailable("base de donnees") from None
    return ReadinessOut(status="ready")


app.include_router(v1_router)
