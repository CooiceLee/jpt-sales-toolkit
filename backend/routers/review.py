"""
Review router - dashboard and map endpoints.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ..repositories.base import ConflictError
from ..services import ReviewService
from .deps import get_current_user

router = APIRouter(prefix="/review", tags=["review"])

SalesStage = Literal["New", "Assigned", "Following", "Quoted", "Won", "Lost"]
Region = Literal["EU", "SEA", "AM", "RIMEA"]
Outcome = Literal["open", "won", "lost"]
ServiceStatus = Literal["None", "Open", "In Progress", "Resolved", "Closed"]
TripStatus = Literal["Draft", "Active", "Completed"]
TripStopResult = Literal["Planned", "Visited", "Follow-up Needed", "Skipped"]
TripTravelMode = Literal["auto", "drive", "ground_public", "flight"]


def get_review_service() -> ReviewService:
    return ReviewService()


def _conflict_http(exc: ConflictError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "conflict",
            "current_version": exc.current_version,
            "your_version": exc.your_version,
            "current_data": exc.current_data,
            "message": "此记录已被他人修改，请刷新后重试",
        },
    )


class TripPlanCreate(BaseModel):
    title: str
    owner_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    region: Optional[Region] = None
    origin_name: Optional[str] = None
    origin_lat: Optional[float] = Field(None, ge=-90, le=90)
    origin_lng: Optional[float] = Field(None, ge=-180, le=180)
    destination_name: Optional[str] = None
    destination_lat: Optional[float] = Field(None, ge=-90, le=90)
    destination_lng: Optional[float] = Field(None, ge=-180, le=180)
    travel_mode: TripTravelMode = "auto"
    avoid_weekends: bool = True
    holiday_dates: Optional[list[str]] = None
    description: Optional[str] = None
    status: TripStatus = "Draft"


class TripPlanUpdate(BaseModel):
    row_version: Optional[int] = Field(None, ge=1)
    title: Optional[str] = None
    owner_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    region: Optional[Region] = None
    origin_name: Optional[str] = None
    origin_lat: Optional[float] = Field(None, ge=-90, le=90)
    origin_lng: Optional[float] = Field(None, ge=-180, le=180)
    destination_name: Optional[str] = None
    destination_lat: Optional[float] = Field(None, ge=-90, le=90)
    destination_lng: Optional[float] = Field(None, ge=-180, le=180)
    travel_mode: Optional[TripTravelMode] = None
    avoid_weekends: Optional[bool] = None
    holiday_dates: Optional[list[str]] = None
    description: Optional[str] = None
    status: Optional[TripStatus] = None


class TripStopCreate(BaseModel):
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    planned_date: Optional[str] = None
    planned_end_date: Optional[str] = None
    stay_days: Optional[int] = Field(None, ge=1, le=30)
    visit_purpose: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = None


class TripStopUpdate(BaseModel):
    row_version: Optional[int] = Field(None, ge=1)
    lead_id: Optional[str] = None
    sequence_no: Optional[int] = None
    planned_date: Optional[str] = None
    planned_end_date: Optional[str] = None
    stay_days: Optional[int] = Field(None, ge=1, le=30)
    visit_purpose: Optional[str] = None
    notes: Optional[str] = None
    result_status: Optional[TripStopResult] = None
    result_notes: Optional[str] = None
    visit_customer_needs: Optional[str] = None
    visit_competitor: Optional[str] = None
    visit_budget: Optional[str] = None
    visit_decision_maker: Optional[str] = None
    visit_next_action: Optional[str] = None
    visit_followup_due_date: Optional[str] = None
    visit_sample_needed: Optional[bool] = None
    visit_quote_needed: Optional[bool] = None


class TripStopReorder(BaseModel):
    stop_ids: list[str]
    row_version: Optional[int] = Field(None, ge=1)


class TripStopArchive(BaseModel):
    row_version: Optional[int] = Field(None, ge=1)


class TripPlanArchive(BaseModel):
    row_version: Optional[int] = Field(None, ge=1)


class TripItineraryGenerate(BaseModel):
    row_version: Optional[int] = Field(None, ge=1)
    start_date: Optional[str] = None
    origin_name: Optional[str] = None
    origin_lat: Optional[float] = Field(None, ge=-90, le=90)
    origin_lng: Optional[float] = Field(None, ge=-180, le=180)
    destination_name: Optional[str] = None
    destination_lat: Optional[float] = Field(None, ge=-90, le=90)
    destination_lng: Optional[float] = Field(None, ge=-180, le=180)
    travel_mode: Optional[TripTravelMode] = None
    avoid_weekends: Optional[bool] = None
    holiday_dates: Optional[list[str]] = None
    stop_stays: Optional[dict[str, int]] = None


@router.get("/dashboard")
async def get_dashboard(
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Get dashboard KPIs and summary data."""
    return service.get_dashboard_data(user["id"], user["role"])


@router.get("/analysis")
async def get_analysis(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    owner_id: Optional[str] = None,
    region: Optional[Region] = None,
    country: Optional[str] = None,
    product_category: Optional[str] = None,
    application: Optional[str] = None,
    sales_stage: Optional[SalesStage] = None,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Get v0.7 read-only business review metrics."""
    return service.get_analysis_data(
        user["id"],
        user["role"],
        date_from=date_from,
        date_to=date_to,
        owner_id=owner_id,
        region=region,
        country=country,
        product_category=product_category,
        application=application,
        sales_stage=sales_stage,
    )


@router.get("/map")
async def get_map_data(
    sales_stage: Optional[SalesStage] = None,
    owner_id: Optional[str] = None,
    outcome: Optional[Outcome] = None,
    service_status: Optional[ServiceStatus] = None,
    region: Optional[Region] = None,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Get customer locations for map display."""
    return service.get_map_data(
        user["id"],
        user["role"],
        sales_stage=sales_stage,
        owner_id=owner_id,
        outcome=outcome,
        service_status=service_status,
        region=region,
    )


@router.get("/trip-candidates")
async def get_trip_candidates(
    region: Optional[Region] = None,
    country: Optional[str] = None,
    owner_id: Optional[str] = None,
    sales_stage: Optional[SalesStage] = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Get scored trip planning customer candidates."""
    return service.get_trip_candidates(
        user["id"],
        user["role"],
        region=region,
        country=country,
        owner_id=owner_id,
        sales_stage=sales_stage,
        limit=limit,
        offset=offset,
    )


@router.get("/trip-plans")
async def list_trip_plans(
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """List saved trip plans."""
    return service.list_trip_plans(user["id"], user["role"])


@router.post("/trip-plans")
async def create_trip_plan(
    request: TripPlanCreate,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Create a trip plan."""
    data = request.model_dump(exclude_none=True)
    if user["role"] != "leader":
        data.pop("owner_id", None)
    return service.create_trip_plan(data, user["id"])


@router.get("/trip-plans/{plan_id}")
async def get_trip_plan(
    plan_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Get a trip plan."""
    plan = service.get_trip_plan(plan_id, user["id"], user["role"])
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return plan


@router.patch("/trip-plans/{plan_id}")
async def update_trip_plan(
    plan_id: str,
    request: TripPlanUpdate,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Update a trip plan."""
    try:
        plan = service.update_trip_plan(
            plan_id,
            request.model_dump(exclude_none=True),
            user["id"],
            user["role"],
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return plan


@router.post("/trip-plans/{plan_id}/generate-itinerary")
async def generate_trip_itinerary(
    plan_id: str,
    request: TripItineraryGenerate,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Generate a scheduled route for the selected trip stops."""
    try:
        plan = service.generate_trip_itinerary(
            plan_id,
            request.model_dump(exclude_none=True),
            user["id"],
            user["role"],
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return plan


@router.post("/trip-plans/{plan_id}/preview-itinerary")
async def preview_trip_itinerary(
    plan_id: str,
    request: TripItineraryGenerate,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Preview a scheduled route without saving it."""
    try:
        plan = service.preview_trip_itinerary(
            plan_id,
            request.model_dump(exclude_none=True),
            user["id"],
            user["role"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return plan


@router.post("/trip-plans/{plan_id}/archive")
async def archive_trip_plan(
    plan_id: str,
    request: Optional[TripPlanArchive] = Body(None),
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Archive a trip plan."""
    try:
        archived = service.archive_trip_plan(
            plan_id,
            user["id"],
            user["role"],
            request.row_version if request else None,
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    if not archived:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return {"status": "archived"}


@router.post("/trip-plans/{plan_id}/stops")
async def add_trip_stop(
    plan_id: str,
    request: TripStopCreate,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Add a stop to a trip plan."""
    try:
        plan = service.add_trip_stop(
            plan_id,
            request.model_dump(exclude_none=True),
            user["id"],
            user["role"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return plan


@router.patch("/trip-plans/{plan_id}/stops/{stop_id}")
async def update_trip_stop(
    plan_id: str,
    stop_id: str,
    request: TripStopUpdate,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Update a trip stop."""
    try:
        plan = service.update_trip_stop(
            plan_id,
            stop_id,
            request.model_dump(exclude_none=True),
            user["id"],
            user["role"],
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip stop not found")
    return plan


@router.post("/trip-plans/{plan_id}/stops/reorder")
async def reorder_trip_stops(
    plan_id: str,
    request: TripStopReorder,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Reorder all active stops in a trip plan."""
    try:
        plan = service.reorder_trip_stops(
            plan_id,
            request.stop_ids,
            user["id"],
            user["role"],
            request.row_version,
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return plan


@router.post("/trip-plans/{plan_id}/stops/{stop_id}/archive")
async def archive_trip_stop(
    plan_id: str,
    stop_id: str,
    request: Optional[TripStopArchive] = Body(None),
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Archive a trip stop."""
    try:
        plan = service.archive_trip_stop(
            plan_id,
            stop_id,
            user["id"],
            user["role"],
            request.row_version if request else None,
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip stop not found")
    return plan


@router.get("/trip-plans/{plan_id}/export.md")
async def export_trip_plan_markdown(
    plan_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Export a trip plan as Markdown."""
    content = service.export_trip_plan_markdown(plan_id, user["id"], user["role"])
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    filename_id = _safe_filename_id(plan_id)
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="trip-plan-{filename_id}.md"'},
    )


@router.get("/trip-plans/{plan_id}/export.csv")
async def export_trip_plan_csv(
    plan_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Export a trip plan as CSV."""
    content = service.export_trip_plan_csv(plan_id, user["id"], user["role"])
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    filename_id = _safe_filename_id(plan_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="trip-plan-{filename_id}.csv"'},
    )


@router.get("/trip-plans/{plan_id}/execution")
async def get_trip_execution(
    plan_id: str,
    date: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Get a day-oriented visit execution view for a trip plan."""
    data = service.get_trip_execution(plan_id, user["id"], user["role"], date)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return data


@router.get("/trip-plans/{plan_id}/execution.md")
async def export_trip_execution_markdown(
    plan_id: str,
    date: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Export one day of itinerary and visit reports as Markdown."""
    content = service.export_trip_execution_markdown(plan_id, user["id"], user["role"], date)
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    filename_id = _safe_filename_id(plan_id)
    date_part = _safe_filename_id(date or "all-days")
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="trip-visit-{filename_id}-{date_part}.md"'},
    )


def _safe_filename_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)
    return safe[:80] or "export"
