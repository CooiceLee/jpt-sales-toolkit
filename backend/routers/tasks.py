"""Aggregate task routes while preserving the public router import."""

from fastapi import APIRouter, Depends

from ..repositories.task_workload_repository import TaskWorkloadRepository
from .after_sales_tasks import router as after_sales_router
from .deps import require_role
from .pre_sales_tasks import router as pre_sales_router
from .task_after_sales_lifecycle import router as after_sales_lifecycle_router


router = APIRouter()
router.include_router(pre_sales_router)
router.include_router(after_sales_router)
router.include_router(after_sales_lifecycle_router)


def get_task_workload_repository() -> TaskWorkloadRepository:
    return TaskWorkloadRepository()


@router.get("/tasks/workload-summary", tags=["tasks"])
async def get_tech_workload_summary(
    user: dict = Depends(require_role("tech")),
    repository: TaskWorkloadRepository = Depends(get_task_workload_repository),
):
    """Return only the signed-in Tech member's active navigation counts."""
    return repository.count_active_leads_for_tech(user["id"])
