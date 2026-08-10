"""Pre-sales task endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..repositories.base import ConflictError
from ..services import PreSalesTaskService
from ..services.permission_policy import TECH_PRE_SALES_UPDATE_FIELDS
from .deps import get_current_user
from .task_dependencies import (
    ensure_task_access,
    ensure_task_creation_allowed,
    ensure_tech_update_fields,
    get_pre_sales_service,
)
from .task_models import PreSalesTaskCreate, PreSalesTaskUpdate, TaskListFilters
from .task_responses import raise_task_update_error


router = APIRouter(tags=["tasks"])


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
    """Create a pre-sales task for a lead."""
    ensure_task_creation_allowed(lead_id, user)
    return service.create(
        lead_id,
        request.model_dump(exclude_none=True),
        user["id"],
    )


@router.patch("/pre-sales-tasks/{task_id}")
async def update_pre_sales_task(
    task_id: str,
    request: PreSalesTaskUpdate,
    user: dict = Depends(get_current_user),
    service: PreSalesTaskService = Depends(get_pre_sales_service),
):
    """Update a pre-sales task."""
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    ensure_task_access(task, user, "update")
    data = request.model_dump(exclude_unset=True, exclude={"row_version"})
    ensure_tech_update_fields(user, data, TECH_PRE_SALES_UPDATE_FIELDS, task)
    try:
        return service.update(task_id, data, user["id"], request.row_version)
    except (ConflictError, ValueError) as error:
        raise_task_update_error(error)


def _get_task_or_404(service: PreSalesTaskService, task_id: str) -> dict:
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/pre-sales-tasks/{task_id}/archive")
async def archive_pre_sales_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: PreSalesTaskService = Depends(get_pre_sales_service),
):
    task = _get_task_or_404(service, task_id)
    ensure_task_access(task, user, "archive")
    if user["role"] == "tech":
        raise HTTPException(status_code=403, detail="Technical users cannot archive tasks")
    if not service.archive(task_id, user["id"]):
        raise HTTPException(status_code=404, detail="Task not found or already archived")
    return {"status": "archived"}


@router.post("/pre-sales-tasks/{task_id}/restore")
async def restore_pre_sales_task(
    task_id: str,
    user: dict = Depends(get_current_user),
    service: PreSalesTaskService = Depends(get_pre_sales_service),
):
    task = _get_task_or_404(service, task_id)
    ensure_task_access(task, user, "restore")
    if user["role"] == "tech":
        raise HTTPException(status_code=403, detail="Technical users cannot restore tasks")
    if not service.restore(task_id, user["id"]):
        raise HTTPException(status_code=404, detail="Task not found or already active")
    return {"status": "restored"}
