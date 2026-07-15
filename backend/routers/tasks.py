"""Aggregate task routes while preserving the public router import."""

from fastapi import APIRouter

from .after_sales_tasks import router as after_sales_router
from .pre_sales_tasks import router as pre_sales_router
from .task_after_sales_lifecycle import router as after_sales_lifecycle_router


router = APIRouter()
router.include_router(pre_sales_router)
router.include_router(after_sales_router)
router.include_router(after_sales_lifecycle_router)
