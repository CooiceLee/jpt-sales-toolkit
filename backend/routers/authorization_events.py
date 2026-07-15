"""Leader-only authorization audit endpoint."""

from fastapi import APIRouter, Depends, Query

from ..services.member_authorization_service import MemberAuthorizationService
from .authorization_dependencies import get_member_service
from .deps import require_role


router = APIRouter()


@router.get("/events")
async def list_authorization_events(
    limit: int = Query(100, ge=1, le=500),
    leader: dict = Depends(require_role("leader")),
    service: MemberAuthorizationService = Depends(get_member_service),
):
    return service.list_events(limit)
