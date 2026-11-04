"""Assemblage des endpoints generaux accessibles selon les droits de l'appelant."""

from fastapi import APIRouter

from app.features.auth.router import router as auth_router
from app.features.networks.router import router as networks_router
from app.features.packs.router import router as packs_router
from app.features.profiles.router import router as profiles_router
from app.features.projects.router import invitations
from app.features.projects.router import router as projects_router
from app.features.requests.router import router as requests_router
from app.features.shares.router import extensions as shares_extensions
from app.features.shares.router import router as shares_router
from app.features.vms.router import router as vms_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(profiles_router)
router.include_router(projects_router)
router.include_router(invitations)
router.include_router(vms_router)
router.include_router(packs_router)
router.include_router(networks_router)
router.include_router(requests_router)
router.include_router(shares_router)
router.include_router(shares_extensions)
