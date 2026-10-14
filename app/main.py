"""Point d'entree FastAPI du backend IaaS.

Le schema est gere par Alembic. Au demarrage, on insere seulement les donnees de reference.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import router as v1_router
from app.core.database import SessionLocal
from app.core.errors import register_exception_handlers
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
from app.shared.seed.seeder import seed_default_packs, seed_default_profiles, seed_rights


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Insere le catalogue de reference si les tables existent deja (apres migration)."""
    with SessionLocal() as db:
        seed_rights(db)
        seed_default_profiles(db)
        seed_default_packs(db)
    yield


app = FastAPI(
    title="IaaS API",
    version="1.0.0",
    summary="Backend metier d'une plateforme IaaS.",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)
register_exception_handlers(app)
app.include_router(v1_router)
