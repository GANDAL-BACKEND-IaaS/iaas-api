"""Assemblage de l'API versionnee /api/v1."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.admin import router as admin_router
from app.api.v1.endpoints import router as endpoints_router
from app.core.database import get_db
from app.core.errors import ErrorCode, error_responses, upstream_unavailable

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


router.include_router(admin_router)
router.include_router(endpoints_router)
