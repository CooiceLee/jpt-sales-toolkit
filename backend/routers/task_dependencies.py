"""Task service dependencies and shared permission checks."""

from fastapi import HTTPException, status

from ..services import AfterSalesTaskService, PreSalesTaskService
from .deps import get_actor_role_for_lead


def get_pre_sales_service() -> PreSalesTaskService:
    return PreSalesTaskService()


def get_after_sales_service() -> AfterSalesTaskService:
    return AfterSalesTaskService()


def ensure_task_access(task: dict, user: dict, action: str) -> None:
    """Enforce related-lead access and own-task boundaries for tech users."""
    actor_role = get_actor_role_for_lead(task["lead_id"], user)
    if user["role"] == "tech":
        if task.get("archived_at"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Technical users cannot modify archived tasks",
            )
        if task.get("assignee_id") != user["id"] or actor_role != "tech":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tech users can only {action} their own active tasks",
            )
        return
    if actor_role in ("none", "watcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


def ensure_tech_update_fields(
    user: dict,
    data: dict,
    allowed_fields: frozenset[str],
) -> None:
    if user["role"] != "tech":
        return
    denied = sorted(set(data) - allowed_fields)
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Technical users cannot update task fields: {', '.join(denied)}",
        )


def ensure_task_creation_allowed(lead_id: str, user: dict) -> None:
    if user["role"] == "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technical users cannot create or assign tasks",
        )
    if get_actor_role_for_lead(lead_id, user) in ("none", "watcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
