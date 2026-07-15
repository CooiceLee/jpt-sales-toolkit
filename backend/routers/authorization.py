"""Offline authorization router assembled from focused endpoint modules."""

from fastapi import APIRouter

from .authorization_admin import router as admin_router
from .authorization_events import router as events_router
from .authorization_issuer import router as issuer_router
from .authorization_public import router as public_router


router = APIRouter(prefix="/authorization", tags=["authorization"])
router.include_router(public_router)
router.include_router(admin_router)
router.include_router(issuer_router)
router.include_router(events_router)


__all__ = ["router"]
