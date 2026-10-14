"""Assemblage de l'API versionnee /api/v1."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ErrorCode, error_responses, upstream_unavailable
from app.features.auth.router import router as auth_router
from app.features.networks.router import router as networks_router
from app.features.packs.router import router as packs_router
from app.features.profiles.router import router as profiles_router
from app.features.projects.router import invitations
from app.features.projects.router import router as projects_router
from app.features.requests.router import router as requests_router
from app.features.shares.router import router as shares_router
from app.features.storages.router import router as storages_router
from app.features.vms.router import router as vms_router

router = APIRouter(prefix="/api/v1")


class HealthOut(BaseModel):
    """Etat de sante de l'API et de sa base."""

    status: str = Field(examples=["ok"])


@router.get(
    "/health",
    response_model=HealthOut,
    operation_id="get_health",
    summary="Sante de l'API",
    tags=["sante"],
    responses=error_responses(ErrorCode.UPSTREAM_UNAVAILABLE),
)
def health(db: Session = Depends(get_db)) -> HealthOut:
    """Verifie que l'API repond et que la base execute une requete simple."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise upstream_unavailable("base de donnees") from None
    return HealthOut(status="ok")


router.include_router(auth_router)
router.include_router(profiles_router)
router.include_router(projects_router)
router.include_router(invitations)
router.include_router(vms_router)
router.include_router(packs_router)
router.include_router(networks_router)
router.include_router(storages_router)
router.include_router(requests_router)
router.include_router(shares_router)
