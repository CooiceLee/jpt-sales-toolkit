"""
Customer router - customer management endpoints.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..services import CustomerService
from ..repositories.base import ConflictError
from .deps import can_access_customer, get_current_user, require_role

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerCreate(BaseModel):
    display_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    customer_type: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    region: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    normalized_address: Optional[str] = None
    geocode_source: Optional[str] = None
    geocode_confidence: Optional[str] = None
    geocode_locked: Optional[bool] = None


class CustomerUpdate(BaseModel):
    display_name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    customer_type: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    address: Optional[str] = None
    region: Optional[str] = None
    language: Optional[str] = None
    company_size: Optional[str] = None
    company_description: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    normalized_address: Optional[str] = None
    geocode_source: Optional[str] = None
    geocode_confidence: Optional[str] = None
    geocode_locked: Optional[bool] = None
    row_version: int


class CustomerMatch(BaseModel):
    email: Optional[str] = None
    company_name: Optional[str] = None


class CustomerMergeRequest(BaseModel):
    source_customer_id: str
    target_customer_id: str
    source_row_version: Optional[int] = None
    target_row_version: Optional[int] = None


class CustomerContactCreate(BaseModel):
    name: str
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    is_primary: bool = True


class CustomerContactUpdate(BaseModel):
    name: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    is_primary: Optional[bool] = None


def get_customer_service() -> CustomerService:
    return CustomerService()


def ensure_customer_access(customer_id: str, user: dict, *, write: bool = False) -> None:
    """Enforce lead-scoped customer access and read-only technical visibility."""
    if not can_access_customer(customer_id, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if write and user["role"] == "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technical users have read-only customer access",
        )


@router.post("")
async def create_customer(
    request: CustomerCreate,
    user: dict = Depends(get_current_user),
    service: CustomerService = Depends(get_customer_service),
):
    """Create new customer."""
    if user["role"] not in {"leader", "sales"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    data = request.model_dump(exclude_none=True)
    return service.create(data, user["id"])


@router.get("")
async def list_customers(
    limit: int = 50,
    offset: int = 0,
    country: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_role("leader")),
    service: CustomerService = Depends(get_customer_service),
):
    """List customers for manual review and merge workflows."""
    return service.list(
        limit=limit,
        offset=offset,
        country=country,
        region=region,
        search=search,
    )


@router.get("/{customer_id}")
async def get_customer(
    customer_id: str,
    user: dict = Depends(get_current_user),
    service: CustomerService = Depends(get_customer_service),
):
    """Get customer by ID."""
    ensure_customer_access(customer_id, user)
    customer = service.get(customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return customer


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: str,
    request: CustomerUpdate,
    user: dict = Depends(get_current_user),
    service: CustomerService = Depends(get_customer_service),
):
    """Update customer."""
    ensure_customer_access(customer_id, user, write=True)
    data = request.model_dump(exclude_none=True, exclude={"row_version"})

    try:
        return service.update(
            customer_id,
            data,
            user["id"],
            request.row_version,
        )
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/{customer_id}/archive")
async def archive_customer(
    customer_id: str,
    user: dict = Depends(require_role("leader")),
    service: CustomerService = Depends(get_customer_service),
):
    """Archive customer (leader only)."""
    success = service.archive(customer_id, user["id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found or already archived",
        )
    return {"status": "archived"}


@router.post("/match")
async def match_customers(
    request: CustomerMatch,
    user: dict = Depends(get_current_user),
    service: CustomerService = Depends(get_customer_service),
):
    """Find potential customer matches."""
    if user["role"] not in {"leader", "sales"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return service.match(request.email, request.company_name)


@router.post("/merge")
async def merge_customers(
    request: CustomerMergeRequest,
    user: dict = Depends(require_role("leader")),
    service: CustomerService = Depends(get_customer_service),
):
    """Merge a duplicate source customer into a target customer."""
    try:
        return service.merge_customers(
            source_customer_id=request.source_customer_id,
            target_customer_id=request.target_customer_id,
            actor_id=user["id"],
            source_row_version=request.source_row_version,
            target_row_version=request.target_row_version,
        )
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
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{customer_id}/contacts")
async def create_customer_contact(
    customer_id: str,
    request: CustomerContactCreate,
    user: dict = Depends(get_current_user),
    service: CustomerService = Depends(get_customer_service),
):
    """Create customer contact."""
    ensure_customer_access(customer_id, user, write=True)
    contact_id = service.add_contact(
        customer_id,
        request.model_dump(exclude_none=True),
        user["id"],
    )
    customer = service.get(customer_id)
    contact = next((item for item in (customer or {}).get("contacts", []) if item["id"] == contact_id), None)
    return contact or {"contact_id": contact_id}


@router.patch("/{customer_id}/contacts/{contact_id}")
async def update_customer_contact(
    customer_id: str,
    contact_id: str,
    request: CustomerContactUpdate,
    user: dict = Depends(get_current_user),
    service: CustomerService = Depends(get_customer_service),
):
    """Update customer contact."""
    ensure_customer_access(customer_id, user, write=True)
    contact = service.customer_repo.get_contact_by_id(contact_id)
    if not contact or contact["customer_id"] != customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    return service.update_contact(
        contact_id,
        request.model_dump(exclude_none=True),
        user["id"],
    )


@router.post("/{customer_id}/contacts/{contact_id}/archive")
async def archive_customer_contact(
    customer_id: str,
    contact_id: str,
    user: dict = Depends(get_current_user),
    service: CustomerService = Depends(get_customer_service),
):
    """Archive customer contact."""
    ensure_customer_access(customer_id, user, write=True)
    contact = service.customer_repo.get_contact_by_id(contact_id)
    if not contact or contact["customer_id"] != customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    success = service.archive_contact(contact_id, user["id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found or already archived",
        )
    return {"status": "archived"}
