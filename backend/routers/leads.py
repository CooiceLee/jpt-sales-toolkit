"""
Lead router - lead management endpoints.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from ..services import LeadService, ActivityService
from ..services.lead_service import (
    InvalidLeadAssignmentError,
    InvalidLeadContactError,
    mask_lead_for_role,
)
from ..services.business_region_service import InvalidBusinessRegionError
from ..repositories.base import ConflictError
from .deps import get_current_user, require_role, get_actor_role_for_lead, get_attachment_service
from .lead_attachment_permissions import (
    filter_attachments_for_user,
    forbid_tech_attachment_access,
    forbid_tech_attachment_write,
)

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    primary_contact_id: Optional[str] = None
    owner_id: str
    title: str
    source_channel: Optional[str] = None
    original_email: Optional[str] = None
    sales_stage: str = "New"
    quality_grade: Optional[str] = None
    product_category: Optional[str] = None
    application: Optional[str] = None
    inquiry_date: Optional[str] = None
    special_requirements: Optional[str] = None
    potential_needs: Optional[str] = None
    products_detail: Optional[str] = None
    quantity_text: Optional[str] = None


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_id: Optional[str] = None
    primary_contact_id: Optional[str] = None
    title: Optional[str] = None
    source_channel: Optional[str] = None
    original_email: Optional[str] = None
    sales_stage: Optional[str] = None
    fulfillment_status: Optional[str] = None
    service_status: Optional[str] = None
    quality_grade: Optional[str] = None
    urgency: Optional[str] = None
    estimated_value: Optional[float] = None
    product_category: Optional[str] = None
    product_series: Optional[str] = None
    power_range: Optional[str] = None
    wavelength: Optional[str] = None
    application: Optional[str] = None
    material: Optional[str] = None
    currency: Optional[str] = None
    deal_amount: Optional[float] = None
    quotation_id: Optional[str] = None
    quotation_date: Optional[str] = None
    po_number: Optional[str] = None
    po_date: Optional[str] = None
    next_followup_date: Optional[str] = None
    inquiry_date: Optional[str] = None
    special_requirements: Optional[str] = None
    potential_needs: Optional[str] = None
    products_detail: Optional[str] = None
    quantity_text: Optional[str] = None
    lost_reason_code: Optional[str] = None
    lost_reason_text: Optional[str] = None
    row_version: int


class AssignmentCreate(BaseModel):
    user_id: str
    assignment_type: str  # owner, collaborator, watcher


class ActivityCreate(BaseModel):
    action_type: str  # follow_up, comment
    content: str
    method: Optional[str] = None  # for follow_up
    status: Optional[str] = None
    response_date: Optional[str] = None
    customer_feedback: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    visibility: str = "all"
    created_at: Optional[str] = None


class ActivityUpdate(BaseModel):
    content: Optional[str] = None
    method: Optional[str] = None
    status: Optional[str] = None
    response_date: Optional[str] = None
    customer_feedback: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    visibility: Optional[str] = None
    created_at: Optional[str] = None


class AttachmentUpdate(BaseModel):
    category: Optional[str] = None
    version_no: Optional[int] = None
    original_name: Optional[str] = None


def get_lead_service() -> LeadService:
    return LeadService()


def get_activity_service() -> ActivityService:
    return ActivityService()


def forbid_tech_activity_write(user: dict) -> None:
    """Tech activity feeds are read-only; task endpoints own all Tech writes."""
    if user["role"] == "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technical users cannot modify lead activities",
        )


@router.post("")
async def create_lead(
    request: LeadCreate,
    user: dict = Depends(get_current_user),
    service: LeadService = Depends(get_lead_service),
):
    """Create new lead."""
    if user["role"] not in {"leader", "sales"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technical users cannot create leads",
        )
    if user["role"] != "leader" and request.owner_id != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Non-leaders can only create leads assigned to themselves",
        )
    data = request.model_dump(exclude_none=True)
    try:
        return service.create(data, user["id"])
    except (InvalidLeadAssignmentError, InvalidLeadContactError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("")
async def list_leads(
    limit: int = 100,
    offset: int = 0,
    owner_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    sales_stage: Optional[str] = None,
    tech_id: Optional[str] = None,
    search: Optional[str] = None,
    business_region: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: LeadService = Depends(get_lead_service),
):
    """List leads with permission filtering."""
    try:
        return service.list(
            actor_id=user["id"],
            actor_role=user["role"],
            limit=limit,
            offset=offset,
            owner_id=owner_id,
            customer_id=customer_id,
            sales_stage=sales_stage,
            tech_id=tech_id,
            search=search,
            business_region=business_region,
        )
    except InvalidBusinessRegionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/{lead_id}")
async def get_lead(
    lead_id: str,
    user: dict = Depends(get_current_user),
    service: LeadService = Depends(get_lead_service),
):
    """Get lead by ID."""
    lead = service.get(lead_id, user["id"], user["role"])
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Permission check
    actor_role = get_actor_role_for_lead(lead_id, user)
    if actor_role == "none" and user["role"] != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return mask_lead_for_role(lead, actor_role)


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str,
    request: LeadUpdate,
    user: dict = Depends(get_current_user),
    service: LeadService = Depends(get_lead_service),
):
    """Update lead."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role == "none":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if actor_role == "tech":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Technical users cannot edit lead sales fields",
        )

    if actor_role == "watcher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Watchers cannot modify leads",
        )

    data = request.model_dump(exclude_unset=True, exclude={"row_version"})
    required_fields = {"owner_id", "title", "sales_stage", "fulfillment_status", "service_status"}
    invalid_nulls = sorted(field for field in required_fields if field in data and data[field] is None)
    if invalid_nulls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Fields cannot be null: {', '.join(invalid_nulls)}",
        )

    try:
        return service.update(
            lead_id,
            data,
            user["id"],
            actor_role,
            request.row_version,
        )
    except (InvalidLeadAssignmentError, InvalidLeadContactError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
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
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/{lead_id}/archive")
async def archive_lead(
    lead_id: str,
    user: dict = Depends(require_role("leader")),
    service: LeadService = Depends(get_lead_service),
):
    """Archive lead (leader only)."""
    success = service.archive(lead_id, user["id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found or already archived",
        )
    return {"status": "archived"}


@router.post("/{lead_id}/assignments")
async def add_assignment(
    lead_id: str,
    request: AssignmentCreate,
    user: dict = Depends(require_role("leader")),
    service: LeadService = Depends(get_lead_service),
):
    """Add assignment to lead (leader only)."""
    try:
        assignment_id = service.add_assignment(
            lead_id,
            request.user_id,
            request.assignment_type,
            user["id"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return {"assignment_id": assignment_id}


@router.post("/{lead_id}/assignments/{assignment_id}/archive")
async def archive_assignment(
    lead_id: str,
    assignment_id: str,
    user: dict = Depends(require_role("leader")),
    service: LeadService = Depends(get_lead_service),
):
    """Archive assignment (leader only)."""
    try:
        success = service.archive_assignment(lead_id, assignment_id, user["id"])
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found or already archived",
        )
    return {"status": "archived"}


@router.get("/{lead_id}/activities")
async def list_activities(
    lead_id: str,
    limit: int = 50,
    offset: int = 0,
    action_type: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
):
    """List activities for a lead with pagination."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role == "none" and user["role"] != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return service.list_for_lead(
        lead_id,
        actor_role,
        limit=limit,
        offset=offset,
        action_type=action_type,
    )


@router.post("/{lead_id}/activities")
async def create_activity(
    lead_id: str,
    request: ActivityCreate,
    user: dict = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
):
    """Create activity (follow-up or comment)."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role == "none" and user["role"] != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Watchers can only comment
    if actor_role == "watcher" and request.action_type != "comment":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Watchers can only add comments",
        )

    forbid_tech_activity_write(user)

    if request.action_type == "follow_up":
        activity_id = service.add_follow_up(
            lead_id=lead_id,
            actor_id=user["id"],
            method=request.method or "Other",
            content=request.content,
            status=request.status or "pending",
            response_date=request.response_date,
            customer_feedback=request.customer_feedback,
            next_action=request.next_action,
            next_action_date=request.next_action_date,
            created_at=request.created_at,
        )
    elif request.action_type == "comment":
        activity_id = service.add_comment(
            lead_id=lead_id,
            actor_id=user["id"],
            comment=request.content,
            visibility=request.visibility,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action_type must be 'follow_up' or 'comment'",
        )

    return {"activity_id": activity_id}


@router.patch("/{lead_id}/activities/{activity_id}")
async def update_activity(
    lead_id: str,
    activity_id: str,
    request: ActivityUpdate,
    user: dict = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
):
    """Update a follow-up activity."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role in ("none", "watcher") and user["role"] != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    forbid_tech_activity_write(user)

    data = request.model_dump(exclude_unset=True)
    try:
        updated = service.update_follow_up(
            activity_id=activity_id,
            lead_id=lead_id,
            actor_id=user["id"],
            **data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    return updated


@router.post("/{lead_id}/activities/{activity_id}/archive")
async def archive_activity(
    lead_id: str,
    activity_id: str,
    user: dict = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
):
    """Archive a follow-up or comment activity."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role in ("none", "watcher") and user["role"] != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    forbid_tech_activity_write(user)

    try:
        success = service.archive(activity_id, lead_id, user["id"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found or already archived",
        )

    return {"status": "archived"}


@router.post("/{lead_id}/activities/{activity_id}/restore")
async def restore_activity(
    lead_id: str,
    activity_id: str,
    user: dict = Depends(get_current_user),
    service: ActivityService = Depends(get_activity_service),
):
    """Restore an archived follow-up or comment activity."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role in ("none", "watcher") and user["role"] != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    forbid_tech_activity_write(user)

    try:
        success = service.restore(activity_id, lead_id, user["id"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found or not archived",
        )

    return {"status": "restored"}


# Attachment endpoints

@router.get("/{lead_id}/attachments")
async def list_attachments(
    lead_id: str,
    category: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service = Depends(get_attachment_service),
):
    """List attachments for a lead."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role == "none" and user["role"] != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return filter_attachments_for_user(service.list_for_lead(lead_id, category), user)


@router.post("/{lead_id}/attachments")
async def upload_attachment(
    lead_id: str,
    category: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    service = Depends(get_attachment_service),
):
    """Upload attachment to a lead."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role in ("none", "watcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    forbid_tech_attachment_write(user)
    try:
        content = await file.read()
        attachment = service.upload(
            lead_id=lead_id,
            category=category,
            filename=file.filename,
            content=content,
            mime_type=file.content_type or "application/octet-stream",
            uploaded_by=user["id"],
        )
        return attachment
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{lead_id}/attachments/{attachment_id}/archive")
async def archive_attachment(
    lead_id: str,
    attachment_id: str,
    user: dict = Depends(get_current_user),
    service = Depends(get_attachment_service),
):
    """Archive an attachment."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role in ("none", "watcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    forbid_tech_attachment_write(user)
    try:
        success = service.archive(attachment_id, lead_id, user["id"])
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found or already archived",
            )
        return {"status": "archived"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.patch("/{lead_id}/attachments/{attachment_id}")
async def update_attachment(
    lead_id: str,
    attachment_id: str,
    request: AttachmentUpdate,
    user: dict = Depends(get_current_user),
    service = Depends(get_attachment_service),
):
    """Update attachment metadata."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role in ("none", "watcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    forbid_tech_attachment_write(user)
    try:
        return service.update_metadata(
            attachment_id=attachment_id,
            lead_id=lead_id,
            actor_id=user["id"],
            **request.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{lead_id}/attachments/{attachment_id}/download")
async def download_attachment(
    lead_id: str,
    attachment_id: str,
    user: dict = Depends(get_current_user),
    service = Depends(get_attachment_service),
):
    """Download an attachment file."""
    actor_role = get_actor_role_for_lead(lead_id, user)

    if actor_role == "none" and user["role"] != "leader":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    forbid_tech_attachment_access(user)
    attachment = service.get_by_id(attachment_id)
    if not attachment or attachment["lead_id"] != lead_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    file_path = service.get_file_path(attachment_id)
    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file not found",
        )

    return FileResponse(
        path=file_path,
        media_type=attachment["mime_type"],
        filename=attachment["original_name"],
    )
