"""
Task router - pre-sales and after-sales task endpoints.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..services import PreSalesTaskService, AfterSalesTaskService
from ..repositories.base import ConflictError
from .deps import get_current_user, get_actor_role_for_lead

router = APIRouter(tags=["tasks"])


class PreSalesTaskCreate(BaseModel):
    assignee_id: Optional[str] = None
    request_json: Optional[str] = None
    due_date: Optional[str] = None


class PreSalesTaskUpdate(BaseModel):
    assignee_id: Optional[str] = None
    status: Optional[str] = None
    request_json: Optional[str] = None
    result_json: Optional[str] = None
    due_date: Optional[str] = None
    row_version: int


class TaskListFilters(BaseModel):
    limit: int = 100
    offset: int = 0
    lead_id: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[str] = None
    include_archived: bool = False


class AfterSalesTaskCreate(BaseModel):
    assignee_id: Optional[str] = None
    issue_type: str
    issue_description: str
    status: Optional[str] = None
    solution: Optional[str] = None
    due_date: Optional[str] = None
    created_at: Optional[str] = None


class AfterSalesTaskUpdate(BaseModel):
    assignee_id: Optional[str] = None
    issue_type: Optional[str] = None
    issue_description: Optional[str] = None
    status: Optional[str] = None
    solution: Optional[str] = None
    due_date: Optional[str] = None
    created_at: Optional[str] = None
    row_version: int


def get_pre_sales_service() -> PreSalesTaskService:
    return PreSalesTaskService()


def get_after_sales_service() -> AfterSalesTaskService:
    return AfterSalesTaskService()


def ensure_task_access(task: dict, user: dict, action: str) -> None:
    """Enforce related-lead access and own-task boundaries for tech users."""
    actor_role = get_actor_role_for_lead(task["lead_id"], user)
    if user["role"] == "tech" and task.get("assignee_id") != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tech users can only {action} their own tasks",
        )
    if actor_role in ("none", "watcher") and user["role"] != "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


# Pre-sales task endpoints

@router.get("/pre-sales-tasks")
async def list_pre_sales_tasks(
    filters: TaskListFilters = Depends(),
    user: dict = Depends(get_current_user),
    service: PreSalesTaskService = Depends(get_pre_sales_service),
):
    """List pre-sales tasks with filters."""
    return service.list(user, filters.model_dump())


@router.post("/leads/{lead_id}/pre-sales-tasks")
async def create_pre_sales_task(
    lead_id: str,
    request: PreSalesTaskCreate,
    user: dict = Depends(get_current_user),
    service: PreSalesTaskService = Depends(get_pre_sales_service),
):
    """Create pre-sales task for a lead."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role in ("none", "watcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    data = request.model_dump(exclude_none=True)
    return service.create(lead_id, data, user["id"])


@router.patch("/pre-sales-tasks/{task_id}")
async def update_pre_sales_task(
    task_id: str,
    request: PreSalesTaskUpdate,
    user: dict = Depends(get_current_user),
    service: PreSalesTaskService = Depends(get_pre_sales_service),
):
    """Update pre-sales task."""
    # Get task to check permissions
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    ensure_task_access(task, user, "update")

    data = request.model_dump(exclude_unset=True, exclude={"row_version"})

    try:
        return service.update(task_id, data, user["id"], request.row_version)
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "conflict",
                "current_version": e.current_version,
                "your_version": e.your_version,
                "current_data": e.current_data,
                "message": "此记录已被他人修改，请刷新后重试",
            },
        )


@router.post("/pre-sales-tasks/{task_id}/archive")
async def archive_pre_sales_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: PreSalesTaskService = Depends(get_pre_sales_service),
):
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    ensure_task_access(task, user, "archive")
    if not service.archive(task_id, user["id"]):
        raise HTTPException(status_code=404, detail="Task not found or already archived")
    return {"status": "archived"}


@router.post("/pre-sales-tasks/{task_id}/restore")
async def restore_pre_sales_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: PreSalesTaskService = Depends(get_pre_sales_service),
):
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    ensure_task_access(task, user, "restore")
    if not service.restore(task_id, user["id"]):
        raise HTTPException(status_code=404, detail="Task not found or already active")
    return {"status": "restored"}


# After-sales task endpoints

@router.get("/after-sales-tasks")
async def list_after_sales_tasks(
    filters: TaskListFilters = Depends(),
    user: dict = Depends(get_current_user),
    service: AfterSalesTaskService = Depends(get_after_sales_service),
):
    """List after-sales tasks with filters."""
    return service.list(user, filters.model_dump())


@router.post("/leads/{lead_id}/after-sales-tasks")
async def create_after_sales_task(
    lead_id: str,
    request: AfterSalesTaskCreate,
    user: dict = Depends(get_current_user),
    service: AfterSalesTaskService = Depends(get_after_sales_service),
):
    """Create after-sales task for a lead."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role in ("none", "watcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    data = request.model_dump(exclude_none=True)
    return service.create(lead_id, data, user["id"])


@router.patch("/after-sales-tasks/{task_id}")
async def update_after_sales_task(
    task_id: str,
    request: AfterSalesTaskUpdate,
    user: dict = Depends(get_current_user),
    service: AfterSalesTaskService = Depends(get_after_sales_service),
):
    """Update after-sales task."""
    # Get task to check permissions
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    ensure_task_access(task, user, "update")

    data = request.model_dump(exclude_unset=True, exclude={"row_version"})

    try:
        return service.update(task_id, data, user["id"], request.row_version)
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "conflict",
                "current_version": e.current_version,
                "your_version": e.your_version,
                "current_data": e.current_data,
                "message": "此记录已被他人修改，请刷新后重试",
            },
        )


@router.post("/after-sales-tasks/{task_id}/archive")
async def archive_after_sales_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: AfterSalesTaskService = Depends(get_after_sales_service),
):
    """Archive after-sales task."""
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    actor_role = get_actor_role_for_lead(task["lead_id"], user)

    if user["role"] == "tech" and task["assignee_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tech users can only archive their own tasks",
        )

    if actor_role in ("none", "watcher") and user["role"] != "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    success = service.archive(task_id, user["id"])
    if not success:
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
    """Restore archived after-sales task."""
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    actor_role = get_actor_role_for_lead(task["lead_id"], user)

    if user["role"] == "tech" and task["assignee_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tech users can only restore their own tasks",
        )

    if actor_role in ("none", "watcher") and user["role"] != "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    success = service.restore(task_id, user["id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or not archived",
        )

    return {"status": "restored"}
