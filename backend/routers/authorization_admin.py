"""Leader-only member directory administration endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..services.member_authorization_service import MemberAuthorizationService
from .authorization_dependencies import get_member_service
from .authorization_http import raise_service_error
from .authorization_models import MemberCreate, MemberUpdate
from .deps import require_role


router = APIRouter()


@router.get("/members")
async def list_members(
    leader: dict = Depends(require_role("leader")),
    service: MemberAuthorizationService = Depends(get_member_service),
):
    return service.list_members()


@router.post("/members", status_code=status.HTTP_201_CREATED)
async def create_member(
    request: MemberCreate,
    leader: dict = Depends(require_role("leader")),
    service: MemberAuthorizationService = Depends(get_member_service),
):
    try:
        return service.create_member(request.model_dump(), leader["id"])
    except ValueError as exc:
        raise_service_error(exc)


@router.patch("/members/{member_id}")
async def update_member(
    member_id: str,
    request: MemberUpdate,
    leader: dict = Depends(require_role("leader")),
    service: MemberAuthorizationService = Depends(get_member_service),
):
    changes = request.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No member changes supplied")
    try:
        return service.update_member(member_id, changes, leader["id"])
    except ValueError as exc:
        raise_service_error(exc)


@router.post("/members/{member_id}/deactivate")
async def deactivate_member(
    member_id: str,
    leader: dict = Depends(require_role("leader")),
    service: MemberAuthorizationService = Depends(get_member_service),
):
    try:
        return service.deactivate_member(member_id, leader["id"])
    except ValueError as exc:
        raise_service_error(exc)


@router.post("/members/{member_id}/reactivate")
async def reactivate_member(
    member_id: str,
    leader: dict = Depends(require_role("leader")),
    service: MemberAuthorizationService = Depends(get_member_service),
):
    try:
        return service.reactivate_member(member_id, leader["id"])
    except ValueError as exc:
        raise_service_error(exc)
