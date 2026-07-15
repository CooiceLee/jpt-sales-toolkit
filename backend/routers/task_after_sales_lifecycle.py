"""After-sales task archive and restore endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..services import AfterSalesTaskService
from .deps import get_actor_role_for_lead, get_current_user
from .task_dependencies import get_after_sales_service


router = APIRouter(tags=["tasks"])


def _get_task_or_404(service: AfterSalesTaskService, task_id: str) -> dict:
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


def _ensure_lifecycle_access(task: dict, user: dict, action: str) -> None:
    actor_role = get_actor_role_for_lead(task["lead_id"], user)
    if user["role"] == "tech" and task["assignee_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tech users can only {action} their own tasks",
        )
    if user["role"] == "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Technical users cannot {action} tasks",
        )
    if actor_role in ("none", "watcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


@router.post("/after-sales-tasks/{task_id}/archive")
async def archive_after_sales_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: AfterSalesTaskService = Depends(get_after_sales_service),
):
    """Archive an after-sales task."""
    task = _get_task_or_404(service, task_id)
    _ensure_lifecycle_access(task, user, "archive")
    if not service.archive(task_id, user["id"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or already archived",
        )
    return {"status": "archived"}


@router.post("/after-sales-tasks/{task_id}/restore")
async def restore_after_sales_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: AfterSalesTaskService = Depends(get_after_sales_service),
):
    """Restore an archived after-sales task."""
    task = _get_task_or_404(service, task_id)
    _ensure_lifecycle_access(task, user, "restore")
    if not service.restore(task_id, user["id"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or not archived",
        )
    return {"status": "restored"}
