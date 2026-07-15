"""After-sales task list, creation and update endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..repositories.base import ConflictError
from ..services import AfterSalesTaskService
from ..services.permission_policy import TECH_AFTER_SALES_UPDATE_FIELDS
from .deps import get_current_user
from .task_dependencies import (
    ensure_task_access,
    ensure_task_creation_allowed,
    ensure_tech_update_fields,
    get_after_sales_service,
)
from .task_models import AfterSalesTaskCreate, AfterSalesTaskUpdate, TaskListFilters
from .task_responses import raise_task_update_error


router = APIRouter(tags=["tasks"])


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
    """Create an after-sales task for a lead."""
    ensure_task_creation_allowed(lead_id, user)
    return service.create(
        lead_id,
        request.model_dump(exclude_none=True),
        user["id"],
    )


@router.patch("/after-sales-tasks/{task_id}")
async def update_after_sales_task(
    task_id: str,
    request: AfterSalesTaskUpdate,
    user: dict = Depends(get_current_user),
    service: AfterSalesTaskService = Depends(get_after_sales_service),
):
    """Update an after-sales task."""
    task = service.task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    ensure_task_access(task, user, "update")
    data = request.model_dump(exclude_unset=True, exclude={"row_version"})
    ensure_tech_update_fields(user, data, TECH_AFTER_SALES_UPDATE_FIELDS)
    try:
        return service.update(task_id, data, user["id"], request.row_version)
    except (ConflictError, ValueError) as error:
        raise_task_update_error(error)
