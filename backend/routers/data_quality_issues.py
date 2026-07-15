"""Imported-data quality prompts and human resolution state."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from ..services.data_quality_issue_service import DataQualityIssueService
from .deps import get_current_user

router = APIRouter(prefix="/data/quality-issues", tags=["data_quality"])


class QualityIssueUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "resolved", "ignored"]
    resolution_note: Optional[str] = None


def get_service() -> DataQualityIssueService:
    return DataQualityIssueService()


@router.get("")
async def list_quality_issues(
    issue_status: Optional[Literal["open", "resolved", "ignored"]] = Query("open", alias="status"),
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    actor: dict = Depends(get_current_user),
    service: DataQualityIssueService = Depends(get_service),
):
    return {
        "items": service.list(actor, {
            "status": issue_status, "entity_type": entity_type,
            "entity_id": entity_id, "limit": limit,
        })
    }


@router.patch("/{issue_id}")
async def update_quality_issue(
    issue_id: str,
    request: QualityIssueUpdate,
    actor: dict = Depends(get_current_user),
    service: DataQualityIssueService = Depends(get_service),
):
    try:
        return service.update(
            issue_id, request.status, request.resolution_note or "", actor
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
