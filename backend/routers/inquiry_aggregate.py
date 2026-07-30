"""Atomic API boundary for the inquiry side-panel save action."""

from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from ..repositories.base import ConflictError, request_db_connection
from ..services.inquiry_aggregate_service import (
    InquiryAggregateService,
    InquiryNotFoundError,
)
from ..services.lead_service import InvalidLeadAssignmentError, InvalidLeadContactError
from .customers import CustomerContactUpdate, CustomerUpdate
from .deps import get_current_user
from .leads import LeadUpdate


router = APIRouter(prefix="/leads", tags=["leads"])


class ContactAggregateUpdate(CustomerContactUpdate):
    model_config = ConfigDict(extra="forbid")

    contact_id: Optional[str] = None
    updated_at: Optional[str] = None


class InquiryAggregateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: Optional[CustomerUpdate] = None
    contact: Optional[ContactAggregateUpdate] = None
    lead: Optional[LeadUpdate] = None


def conflict_detail(exc: ConflictError) -> dict:
    return {
        "error": "conflict",
        "current_version": exc.current_version,
        "your_version": exc.your_version,
        "current_data": exc.current_data,
        "message": "此记录已被他人修改，请刷新后重试",
    }


@router.patch("/{lead_id}/aggregate")
def save_inquiry_aggregate(
    lead_id: str,
    request: InquiryAggregateUpdate,
    user: dict = Depends(get_current_user),
):
    """Save the inquiry's customer, contact and lead as one all-or-nothing edit."""
    if request.customer is None and request.contact is None and request.lead is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one inquiry section is required",
        )

    customer = (
        request.customer.model_dump(exclude_none=True)
        if request.customer is not None
        else None
    )
    contact = (
        request.contact.model_dump(exclude_none=True)
        if request.contact is not None
        else None
    )
    lead = (
        request.lead.model_dump(exclude_unset=True)
        if request.lead is not None
        else None
    )
    try:
        with request_db_connection() as conn:
            return InquiryAggregateService(conn).save(
                lead_id,
                user,
                customer=customer,
                contact=contact,
                lead=lead,
            )
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=conflict_detail(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except InquiryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (InvalidLeadAssignmentError, InvalidLeadContactError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Update violates an inquiry data constraint",
        ) from exc
