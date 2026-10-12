from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import SessionLocal, engine
from app.features.auth.router import router as auth_router
from app.features.profiles.router import router as profiles_router
from app.shared.models import identities, rights  # noqa: F401  (enregistre les tables)
from app.shared.models.base import Base
from app.shared.seed.seeder import seed_default_profiles, seed_rights


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # provisoire, remplacé par Alembic ensuite
    with SessionLocal() as db:
        seed_rights(db)
        seed_default_profiles(db)
    yield


app = FastAPI(title="IaaS API", lifespan=lifespan)

app.include_router(profiles_router)
app.include_router(auth_router)
