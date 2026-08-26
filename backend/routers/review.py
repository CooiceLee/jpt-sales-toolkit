"""
Review router - dashboard and map endpoints.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ..repositories.base import ConflictError
from ..services import ReviewService
from .deps import get_current_user, require_role

router = APIRouter(
    prefix="/review",
    tags=["review"],
    dependencies=[Depends(require_role("leader", "sales"))],
)

SalesStage = Literal["New", "Assigned", "Following", "Quoted", "Won", "Lost"]
Region = Literal["EU", "SEA", "AM", "RIMEA"]
Outcome = Literal["open", "won", "lost"]
ServiceStatus = Literal["None", "Open", "In Progress", "Resolved", "Closed"]
TripStatus = Literal["Draft", "Active", "Completed"]
TripStopResult = Literal["Planned", "Visited", "Follow-up Needed", "Skipped"]
TripTravelMode = Literal["auto", "drive", "ground_public", "flight", "other"]
TripTransportMode = Literal["flight", "drive", "ground_public", "other"]
TripRouteOrderMode = Literal["auto", "manual"]
TripFreeStopCategory = Literal["rest", "hotel", "airport", "transit", "meal", "other"]
TripPeriod = Literal["auto", "AM", "PM"]
TripPlannedPeriod = Literal["AM", "PM"]
TripConfirmationStatus = Literal[
    "unconfirmed", "tentative", "confirmed", "needs_reconfirmation", "cancelled"
]


class TripLegOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_mode: Optional[TripTransportMode] = None
    mode_locked: Optional[bool] = None
    manual_distance_km: Optional[float] = Field(None, ge=0)
    manual_time_hours: Optional[float] = Field(None, ge=0)
    manual_travel_days: Optional[int] = Field(None, ge=0)
    manual_travel_half_days: Optional[int] = Field(None, ge=0, le=60)
    notes: Optional[str] = None
    # Airports belong to the flown connection; coordinates always come from a
    # location search, never from the user typing them.
    departure_airport_name: Optional[str] = Field(None, max_length=200)
    departure_airport_lat: Optional[float] = Field(None, ge=-90, le=90)
    departure_airport_lng: Optional[float] = Field(None, ge=-180, le=180)
    departure_airport_stay_half_days: Optional[int] = Field(None, ge=0, le=60)
    arrival_airport_name: Optional[str] = Field(None, max_length=200)
    arrival_airport_lat: Optional[float] = Field(None, ge=-90, le=90)
    arrival_airport_lng: Optional[float] = Field(None, ge=-180, le=180)
    arrival_airport_stay_half_days: Optional[int] = Field(None, ge=0, le=60)


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


TripPlanningMode = Literal["legacy", "team"]


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
    route_order_mode: TripRouteOrderMode = "auto"
    transport_mode_priority: Optional[list[TripTransportMode]] = None
    departure_window_start: Optional[str] = None
    departure_window_end: Optional[str] = None
    return_window_start: Optional[str] = None
    return_window_end: Optional[str] = None
    avoid_weekends: bool = True
    holiday_dates: Optional[list[str]] = None
    description: Optional[str] = None
    status: TripStatus = "Draft"
    planning_mode: TripPlanningMode = "legacy"


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
    route_order_mode: Optional[TripRouteOrderMode] = None
    transport_mode_priority: Optional[list[TripTransportMode]] = None
    departure_window_start: Optional[str] = None
    departure_window_end: Optional[str] = None
    return_window_start: Optional[str] = None
    return_window_end: Optional[str] = None
    avoid_weekends: Optional[bool] = None
    holiday_dates: Optional[list[str]] = None
    description: Optional[str] = None
    status: Optional[TripStatus] = None
    planning_mode: Optional[TripPlanningMode] = None


class TripStopCreate(BaseModel):
    customer_id: Optional[str] = None
    lead_id: Optional[str] = None
    planned_date: Optional[str] = None
    planned_end_date: Optional[str] = None
    stay_days: Optional[int] = Field(None, ge=1, le=30)
    duration_half_days: Optional[int] = Field(None, ge=1, le=60)
    preferred_period: TripPeriod = "auto"
    planned_start_period: Optional[TripPlannedPeriod] = None
    planned_end_period: Optional[TripPlannedPeriod] = None
    schedule_locked: bool = False
    confirmation_status: TripConfirmationStatus = "unconfirmed"
    visit_purpose: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = None
    allow_duplicate: bool = False


class TripStopUpdate(BaseModel):
    row_version: Optional[int] = Field(None, ge=1)
    lead_id: Optional[str] = None
    sequence_no: Optional[int] = None
    planned_date: Optional[str] = None
    planned_end_date: Optional[str] = None
    stay_days: Optional[int] = Field(None, ge=1, le=30)
    duration_half_days: Optional[int] = Field(None, ge=1, le=60)
    preferred_period: Optional[TripPeriod] = None
    planned_start_period: Optional[TripPlannedPeriod] = None
    planned_end_period: Optional[TripPlannedPeriod] = None
    schedule_locked: Optional[bool] = None
    confirmation_status: Optional[TripConfirmationStatus] = None
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


class TripMemberUpsert(BaseModel):
    """A team account travelling on this plan, with optional own endpoints."""

    user_id: str
    origin_name_override: Optional[str] = None
    origin_lat_override: Optional[float] = None
    origin_lng_override: Optional[float] = None
    destination_name_override: Optional[str] = None
    destination_lat_override: Optional[float] = None
    destination_lng_override: Optional[float] = None


class TripFreeStopCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: TripFreeStopCategory
    location_name: str = Field(min_length=1, max_length=200)
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    stay_days: Optional[int] = Field(None, ge=1, le=30)
    duration_half_days: Optional[int] = Field(None, ge=1, le=60)
    preferred_period: TripPeriod = "auto"
    planned_start_period: Optional[TripPlannedPeriod] = None
    planned_end_period: Optional[TripPlannedPeriod] = None
    schedule_locked: bool = False
    confirmation_status: TripConfirmationStatus = "unconfirmed"
    visit_purpose: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = Field(None, ge=1)
    participant_user_ids: Optional[list[str]] = None


class TripFreeStopUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: Optional[int] = Field(None, ge=1)
    category: Optional[TripFreeStopCategory] = None
    location_name: Optional[str] = Field(None, min_length=1, max_length=200)
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    stay_days: Optional[int] = Field(None, ge=1, le=30)
    duration_half_days: Optional[int] = Field(None, ge=1, le=60)
    preferred_period: Optional[TripPeriod] = None
    planned_start_period: Optional[TripPlannedPeriod] = None
    planned_end_period: Optional[TripPlannedPeriod] = None
    schedule_locked: Optional[bool] = None
    confirmation_status: Optional[TripConfirmationStatus] = None
    visit_purpose: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = Field(None, ge=1)
    participant_user_ids: Optional[list[str]] = None


class TripFreeStopArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: Optional[int] = Field(None, ge=1)


class TripPlanArchive(BaseModel):
    row_version: Optional[int] = Field(None, ge=1)


class TripBriefingLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    use_customer_default: bool = True


class TripBriefingCustomerTeam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = Field(None, ge=1)


class TripBriefingContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_contact_id: Optional[str] = None
    name: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = Field(None, ge=1)


class TripBriefingParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    display_name: Optional[str] = None
    role: Optional[str] = None
    responsibility: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = Field(None, ge=1)


class TripBriefingChannelPartnerCompanion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: Optional[str] = None
    name: str = Field(min_length=1)
    position: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = Field(None, ge=1)


class TripBriefingEquipment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["demo", "po", "other"]
    model: Optional[str] = None
    specification: Optional[str] = None
    quantity: Optional[str] = None
    owner_team: Optional[str] = None
    notes: Optional[str] = None
    sequence_no: Optional[int] = Field(None, ge=1)


class TripBriefingAgendaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    owner: Optional[str] = None
    preparation: Optional[str] = None
    expected_outcome: Optional[str] = None
    sequence_no: Optional[int] = Field(None, ge=1)


class TripVisitBriefingPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: Optional[int] = Field(None, ge=1)
    stop_row_version: int = Field(ge=1)
    confirmation_status: TripConfirmationStatus = "unconfirmed"
    timezone: Optional[str] = None
    location: TripBriefingLocation = Field(default_factory=TripBriefingLocation)
    customer_team: list[TripBriefingCustomerTeam] = Field(default_factory=list)
    contacts: list[TripBriefingContact] = Field(default_factory=list)
    participants: list[TripBriefingParticipant] = Field(default_factory=list)
    channel_partner_companions: list[TripBriefingChannelPartnerCompanion] = Field(
        default_factory=list
    )
    equipment: list[TripBriefingEquipment] = Field(default_factory=list)
    agenda_items: list[TripBriefingAgendaItem] = Field(default_factory=list)


class TripStopDurationOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    half_days: Optional[int] = Field(None, ge=1, le=60)
    preferred_period: Optional[TripPeriod] = None
    locked: Optional[bool] = None


class TripItineraryGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: Optional[int] = Field(None, ge=1)
    title: Optional[str] = Field(None, min_length=1, max_length=200)
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
    route_order_mode: Optional[TripRouteOrderMode] = None
    transport_mode_priority: Optional[list[TripTransportMode]] = None
    departure_window_start: Optional[str] = None
    departure_window_end: Optional[str] = None
    return_window_start: Optional[str] = None
    return_window_end: Optional[str] = None
    avoid_weekends: Optional[bool] = None
    holiday_dates: Optional[list[str]] = None
    description: Optional[str] = None
    stop_stays: Optional[dict[str, int]] = None
    stop_durations: Optional[dict[str, TripStopDurationOverride]] = None
    stop_order: Optional[list[str]] = None
    leg_overrides: Optional[dict[str, TripLegOverride]] = None


class TripTransportSuggestionsRequest(TripItineraryGenerate):
    force_refresh: bool = False


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
    try:
        return service.create_trip_plan(data, user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


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


@router.get("/trip-plans/{plan_id}/stops/{stop_id}/briefing")
async def get_trip_visit_briefing(
    plan_id: str,
    stop_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Get the saved visit briefing plus explicit Lead/contact suggestions."""
    briefing = service.get_trip_visit_briefing(
        plan_id, stop_id, user["id"], user["role"]
    )
    if briefing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trip stop not found"
        )
    return briefing


@router.put("/trip-plans/{plan_id}/stops/{stop_id}/briefing")
async def put_trip_visit_briefing(
    plan_id: str,
    stop_id: str,
    request: TripVisitBriefingPut,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Atomically replace a visit briefing using stop and briefing CAS versions."""
    try:
        briefing = service.put_trip_visit_briefing(
            plan_id,
            stop_id,
            request.model_dump(),
            user["id"],
            user["role"],
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if briefing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trip stop not found"
        )
    return briefing


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
            request.model_dump(exclude_unset=True),
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
            request.model_dump(exclude_unset=True),
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
            request.model_dump(exclude_unset=True),
            user["id"],
            user["role"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return plan


@router.post("/trip-plans/{plan_id}/transport-suggestions")
async def get_trip_transport_suggestions(
    plan_id: str,
    request: TripTransportSuggestionsRequest,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Return read-only, manually confirmed suggestions for previewed legs."""
    data = request.model_dump(exclude_unset=True)
    force_refresh = bool(data.pop("force_refresh", False))
    try:
        result = service.get_trip_transport_suggestions(
            plan_id,
            data,
            user["id"],
            user["role"],
            force_refresh=force_refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return result


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
            request.model_dump(exclude_unset=True),
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


@router.put("/trip-plans/{plan_id}/members")
async def set_trip_member(
    plan_id: str,
    request: TripMemberUpsert,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Add a team member to the trip, or change where they travel from."""
    try:
        plan = service.set_trip_member(
            plan_id,
            request.model_dump(exclude_unset=True),
            user["id"],
            user["role"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    return plan


@router.delete("/trip-plans/{plan_id}/members/{user_id}")
async def remove_trip_member(
    plan_id: str,
    user_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Take a team member off the trip."""
    try:
        plan = service.remove_trip_member(
            plan_id, user_id, user["id"], user["role"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip member not found")
    return plan


@router.post("/trip-plans/{plan_id}/free-stops")
async def add_trip_free_stop(
    plan_id: str,
    request: TripFreeStopCreate,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Add a route stop that is independent from customers and Leads."""
    try:
        plan = service.add_trip_free_stop(
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


@router.patch("/trip-plans/{plan_id}/free-stops/{free_stop_id}")
async def update_trip_free_stop(
    plan_id: str,
    free_stop_id: str,
    request: TripFreeStopUpdate,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Update an independent route stop."""
    try:
        plan = service.update_trip_free_stop(
            plan_id,
            free_stop_id,
            request.model_dump(exclude_unset=True),
            user["id"],
            user["role"],
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Free stop not found")
    return plan


@router.post("/trip-plans/{plan_id}/free-stops/{free_stop_id}/archive")
async def archive_trip_free_stop(
    plan_id: str,
    free_stop_id: str,
    request: Optional[TripFreeStopArchive] = Body(None),
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Archive an independent route stop."""
    try:
        plan = service.archive_trip_free_stop(
            plan_id,
            free_stop_id,
            user["id"],
            user["role"],
            request.row_version if request else None,
        )
    except ConflictError as exc:
        raise _conflict_http(exc)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Free stop not found")
    return plan


@router.get("/trip-plans/{plan_id}/export.md")
async def export_trip_plan_markdown(
    plan_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Export a trip plan as Markdown."""
    try:
        content = service.export_trip_plan_markdown(plan_id, user["id"], user["role"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
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
    try:
        content = service.export_trip_plan_csv(plan_id, user["id"], user["role"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    filename_id = _safe_filename_id(plan_id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="trip-plan-{filename_id}.csv"'},
    )


def _formal_export_response(
    content: Optional[bytes], plan_id: str, extension: str, media_type: str
) -> Response:
    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip plan not found")
    filename_id = _safe_filename_id(plan_id)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="trip-plan-{filename_id}.{extension}"'},
    )


@router.get("/trip-plans/{plan_id}/export.xlsx")
async def export_trip_plan_xlsx(
    plan_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    try:
        content = service.export_trip_plan_xlsx(plan_id, user["id"], user["role"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _formal_export_response(
        content, plan_id, "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/trip-plans/{plan_id}/export.html")
async def export_trip_plan_html(
    plan_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    try:
        content = service.export_trip_plan_html(plan_id, user["id"], user["role"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _formal_export_response(content, plan_id, "html", "text/html; charset=utf-8")


@router.get("/trip-plans/{plan_id}/export.ics")
async def export_trip_plan_ics(
    plan_id: str,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    try:
        content = service.export_trip_plan_ics(plan_id, user["id"], user["role"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _formal_export_response(content, plan_id, "ics", "text/calendar; charset=utf-8")


@router.get("/trip-plans/{plan_id}/execution")
async def get_trip_execution(
    plan_id: str,
    date: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Get a day-oriented visit execution view for a trip plan."""
    try:
        data = service.get_trip_execution(plan_id, user["id"], user["role"], date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
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
    try:
        content = service.export_trip_execution_markdown(
            plan_id, user["id"], user["role"], date
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
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
