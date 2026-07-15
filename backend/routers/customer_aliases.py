"""Customer alias CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..services.customer_alias_service import CustomerAliasService
from .deps import can_access_customer, get_current_user, require_role

router = APIRouter()


class CustomerAliasPayload(BaseModel):
    alias_name: str


def get_alias_service() -> CustomerAliasService:
    return CustomerAliasService()


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{customer_id}/aliases")
async def list_customer_aliases(
    customer_id: str,
    include_archived: bool = False,
    user: dict = Depends(get_current_user),
    service: CustomerAliasService = Depends(get_alias_service),
):
    if not can_access_customer(customer_id, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if include_archived and user["role"] != "leader":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Leader access required")
    return service.list(customer_id, include_archived)


@router.post("/{customer_id}/aliases")
async def create_customer_alias(
    customer_id: str,
    request: CustomerAliasPayload,
    user: dict = Depends(require_role("leader")),
    service: CustomerAliasService = Depends(get_alias_service),
):
    try:
        return service.create(customer_id, request.alias_name, user["id"])
    except (ValueError, RuntimeError) as exc:
        raise _translate_error(exc)


@router.patch("/{customer_id}/aliases/{alias_id}")
async def update_customer_alias(
    customer_id: str,
    alias_id: str,
    request: CustomerAliasPayload,
    user: dict = Depends(require_role("leader")),
    service: CustomerAliasService = Depends(get_alias_service),
):
    try:
        return service.update(customer_id, alias_id, request.alias_name, user["id"])
    except (ValueError, RuntimeError) as exc:
        raise _translate_error(exc)


@router.post("/{customer_id}/aliases/{alias_id}/archive")
async def archive_customer_alias(
    customer_id: str,
    alias_id: str,
    user: dict = Depends(require_role("leader")),
    service: CustomerAliasService = Depends(get_alias_service),
):
    try:
        return service.archive(customer_id, alias_id, user["id"])
    except (ValueError, RuntimeError) as exc:
        raise _translate_error(exc)


@router.post("/{customer_id}/aliases/{alias_id}/restore")
async def restore_customer_alias(
    customer_id: str,
    alias_id: str,
    user: dict = Depends(require_role("leader")),
    service: CustomerAliasService = Depends(get_alias_service),
):
    try:
        return service.restore(customer_id, alias_id, user["id"])
    except (ValueError, RuntimeError) as exc:
        raise _translate_error(exc)
