"""Geocoding endpoints mounted under the intake router."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..services import GeocodeService
from ..services.geocoding import GeocodingError
from .deps import get_current_user


router = APIRouter()


class GeocodeRequest(BaseModel):
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    limit: int = Field(5, ge=1, le=5)
    provider: Optional[str] = None


def get_geocode_service() -> GeocodeService:
    return GeocodeService()


def _geocoding_http_error(exc: GeocodingError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.as_detail())


@router.post("/geocode/search")
def search_addresses(
    request: GeocodeRequest,
    user: dict = Depends(get_current_user),
    service: GeocodeService = Depends(get_geocode_service),
):
    """Return up to five WGS84 candidates without changing customer data."""
    try:
        return service.search(
            address=request.address,
            city=request.city,
            postal_code=request.postal_code,
            country=request.country,
            limit=request.limit,
            provider=request.provider,
        )
    except GeocodingError as exc:
        raise _geocoding_http_error(exc) from exc


@router.post("/geocode")
def geocode_address(
    request: GeocodeRequest,
    user: dict = Depends(get_current_user),
    service: GeocodeService = Depends(get_geocode_service),
):
    """Convert an address to WGS84 coordinates."""
    try:
        result = service.geocode(
            address=request.address,
            city=request.city,
            postal_code=request.postal_code,
            country=request.country,
        )
    except GeocodingError as exc:
        raise _geocoding_http_error(exc) from exc

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found",
        )
    return result
