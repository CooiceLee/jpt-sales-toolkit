"""Leader-only customer merge preview and execution endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..repositories.base import ConflictError
from ..services.customer_service import CustomerService
from ..services.customer_merge_service import CustomerMergeService
from .deps import require_role

router = APIRouter()


class CustomerMergeRequest(BaseModel):
    source_customer_id: str
    target_customer_id: str
    source_row_version: int
    target_row_version: int


def get_merge_service() -> CustomerMergeService:
    return CustomerMergeService()


def get_customer_service() -> CustomerService:
    return CustomerService()


def _raise_merge_error(exc: Exception) -> None:
    if isinstance(exc, ConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "conflict",
                "current_version": exc.current_version,
                "your_version": exc.your_version,
                "current_data": exc.current_data,
                "message": "此记录已被修改，请刷新后重试",
            },
        )
    code = status.HTTP_503_SERVICE_UNAVAILABLE if isinstance(exc, RuntimeError) else status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail=str(exc))


@router.get("/merge/candidates")
async def list_customer_merge_candidates(
    query: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(12, ge=1, le=50),
    user: dict = Depends(require_role("leader")),
    service: CustomerService = Depends(get_customer_service),
):
    """Return fuzzy name/alias candidates without exposing archived customers."""
    try:
        return service.fuzzy_merge_candidates(query, limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/merge/preview")
async def preview_customer_merge(
    request: CustomerMergeRequest,
    user: dict = Depends(require_role("leader")),
    service: CustomerMergeService = Depends(get_merge_service),
):
    try:
        return service.preview(
            request.source_customer_id, request.target_customer_id,
            request.source_row_version, request.target_row_version,
        )
    except (ConflictError, ValueError, RuntimeError) as exc:
        _raise_merge_error(exc)


@router.post("/merge")
async def merge_customers(
    request: CustomerMergeRequest,
    user: dict = Depends(require_role("leader")),
    service: CustomerMergeService = Depends(get_merge_service),
):
    try:
        return service.merge(
            request.source_customer_id, request.target_customer_id, user["id"],
            request.source_row_version, request.target_row_version,
        )
    except (ConflictError, ValueError, RuntimeError) as exc:
        _raise_merge_error(exc)
