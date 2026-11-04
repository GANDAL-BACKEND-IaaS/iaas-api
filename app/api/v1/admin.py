"""Assemblage des endpoints reserves aux administrateurs."""

from fastapi import APIRouter

from app.features.auth.router import admin_router as accounts_router
from app.features.packs.router import admin_router as packs_router
from app.features.profiles.router import admin_router as profiles_router
from app.features.requests.router import admin_router as requests_router

router = APIRouter()

router.include_router(accounts_router)
router.include_router(profiles_router)
router.include_router(packs_router)
router.include_router(requests_router)
