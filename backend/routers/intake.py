"""
Intake router - email parsing and combined lead creation.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..services import IntakeService, GeocodeService
from .deps import get_current_user

router = APIRouter(prefix="/intake", tags=["intake"])


class ParseEmailRequest(BaseModel):
    raw_email: str


class IntakeSubmitRequest(BaseModel):
    is_new_customer: bool
    customer_id: Optional[str] = None
    customer: Optional[dict] = None
    contact: Optional[dict] = None
    lead: dict
    owner_id: str
    collaborator_ids: Optional[list[str]] = None
    watcher_ids: Optional[list[str]] = None


class GeocodeRequest(BaseModel):
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None


def get_intake_service() -> IntakeService:
    return IntakeService()


def get_geocode_service() -> GeocodeService:
    return GeocodeService()


@router.post("/parse-email")
async def parse_email(
    request: ParseEmailRequest,
    user: dict = Depends(get_current_user),
    service: IntakeService = Depends(get_intake_service),
):
    """Parse raw email and extract structured fields."""
    return service.parse_email(request.raw_email)


@router.post("/submit")
async def submit_intake(
    request: IntakeSubmitRequest,
    user: dict = Depends(get_current_user),
    service: IntakeService = Depends(get_intake_service),
):
    """
    Atomic submission of customer + lead + assignments.

    One-screen intake creates everything in a single transaction.
    """
    try:
        if user["role"] != "leader" and request.owner_id != user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Non-leaders can only create leads assigned to themselves",
            )
        return service.submit(
            is_new_customer=request.is_new_customer,
            customer_id=request.customer_id,
            customer_data=request.customer,
            lead_data=request.lead,
            contact_data=request.contact,
            owner_id=request.owner_id,
            actor_id=user["id"],
            collaborator_ids=request.collaborator_ids,
            watcher_ids=request.watcher_ids,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/geocode")
async def geocode_address(
    request: GeocodeRequest,
    user: dict = Depends(get_current_user),
    service: GeocodeService = Depends(get_geocode_service),
):
    """Convert address to coordinates."""
    result = service.geocode(
        address=request.address,
        city=request.city,
        country=request.country,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found",
        )

    return result
