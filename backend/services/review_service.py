"""
Review service - dashboard KPIs and map data.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from ..repositories import (
    ActivityRepository,
    CustomerRepository,
    LeadRepository,
    PreSalesReadRepository,
)
from ..repositories.base import ConflictError, generate_uuid, now_iso
from .country_service import CountryService
from .review_analysis_service import ReviewAnalysisService
from .review_map_service import ReviewMapService
from .review_utils import clean_stay_days, csv_cell, finite_float, md_cell, num, parse_date, parse_holiday_dates
from .trip_leg_contract import (
    normalize_overrides,
    normalize_priority,
    validate_route_order_mode,
    validate_stop_order,
    validate_time_windows,
)
from .trip_leg_engine import build_leg, select_mode, travel_calendar_half_days
from .trip_flight_expansion import airport_point, ground_mode, is_expandable
from .trip_flight_waypoints import (
    anchor_waypoints,
    apply_flight_waypoints,
    flight_leg_indices,
    split_waypoints,
)
from .trip_plan_service import TripPlanService
from .visibility_service import VisibilityService

RISK_SCORE_WEIGHTS = {
    "overdue_followup": 40,
    "stale_activity": 30,
    "high_value": 20,
    "quoted": 15,
}

TRIP_SCORE_WEIGHTS = {
    "open_lead": 20,
    "quoted": 25,
    "following": 15,
    "pipeline_value_divisor": 10000,
    "pipeline_value_cap": 40,
    "service_context": 12,
    "coordinate_review_penalty": 8,
}

TRIP_TRAVEL_MODES = {"auto", "drive", "ground_public", "flight", "other"}


class ReviewService:
    """Review and analytics service."""

    def __init__(
        self,
        lead_repo: Optional[LeadRepository] = None,
        customer_repo: Optional[CustomerRepository] = None,
        activity_repo: Optional[ActivityRepository] = None,
        pre_sales_read_repo: Optional[PreSalesReadRepository] = None,
    ):
        self.lead_repo = lead_repo or LeadRepository()
        self.customer_repo = customer_repo or CustomerRepository()
        self.activity_repo = activity_repo or ActivityRepository()
        self.pre_sales_read_repo = pre_sales_read_repo or PreSalesReadRepository(
            self.lead_repo.conn
        )
        self.country_service = CountryService()
        self.country_lookup = self.country_service.lookup
        self.visibility_service = VisibilityService(self)
        self.analysis_service = ReviewAnalysisService(self)
        self.map_service = ReviewMapService(self)
        self.trip_plan_service = TripPlanService(self)

    def get_analysis_data(
        self,
        actor_id: str,
        actor_role: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        owner_id: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None,
        product_category: Optional[str] = None,
        application: Optional[str] = None,
        sales_stage: Optional[str] = None,
    ) -> dict:
        return self.analysis_service.get_analysis_data(actor_id, actor_role, date_from, date_to, owner_id, region, country, product_category, application, sales_stage)

    def get_trip_candidates(
        self,
        actor_id: str,
        actor_role: str,
        region: Optional[str] = None,
        country: Optional[str] = None,
        owner_id: Optional[str] = None,
        sales_stage: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        return self.trip_plan_service.get_trip_candidates(actor_id, actor_role, region, country, owner_id, sales_stage, limit, offset)

    def get_dashboard_data(
        self,
        actor_id: str,
        actor_role: str,
    ) -> dict:
        return self.analysis_service.get_dashboard_data(actor_id, actor_role)

    def get_map_data(
        self,
        actor_id: str,
        actor_role: str,
        sales_stage: Optional[str] = None,
        owner_id: Optional[str] = None,
        outcome: Optional[str] = None,
        service_status: Optional[str] = None,
        region: Optional[str] = None,
    ) -> dict:
        return self.map_service.get_map_data(actor_id, actor_role, sales_stage, owner_id, outcome, service_status, region)

    def list_trip_plans(self, actor_id: str, actor_role: str) -> list[dict]:
        return self.trip_plan_service.list_trip_plans(actor_id, actor_role)

    def create_trip_plan(self, data: dict, actor_id: str) -> dict:
        return self.trip_plan_service.create_trip_plan(data, actor_id)

    def get_trip_plan(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[dict]:
        return self.trip_plan_service.get_trip_plan(plan_id, actor_id, actor_role)

    def update_trip_plan(self, plan_id: str, data: dict, actor_id: str, actor_role: str) -> Optional[dict]:
        return self.trip_plan_service.update_trip_plan(plan_id, data, actor_id, actor_role)

    def get_trip_visit_briefing(
        self, plan_id: str, stop_id: str, actor_id: str, actor_role: str
    ) -> Optional[dict]:
        return self.trip_plan_service.get_trip_visit_briefing(
            plan_id, stop_id, actor_id, actor_role
        )

    def put_trip_visit_briefing(
        self,
        plan_id: str,
        stop_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        return self.trip_plan_service.put_trip_visit_briefing(
            plan_id, stop_id, data, actor_id, actor_role
        )

    def archive_trip_plan(
        self,
        plan_id: str,
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> bool:
        return self.trip_plan_service.archive_trip_plan(plan_id, actor_id, actor_role, row_version)

    def add_trip_stop(self, plan_id: str, data: dict, actor_id: str, actor_role: str) -> Optional[dict]:
        return self.trip_plan_service.add_trip_stop(plan_id, data, actor_id, actor_role)

    def update_trip_stop(
        self,
        plan_id: str,
        stop_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        return self.trip_plan_service.update_trip_stop(plan_id, stop_id, data, actor_id, actor_role)

    def reorder_trip_stops(
        self,
        plan_id: str,
        stop_ids: list[str],
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> Optional[dict]:
        return self.trip_plan_service.reorder_trip_stops(plan_id, stop_ids, actor_id, actor_role, row_version)

    def generate_trip_itinerary(
        self,
        plan_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        return self.trip_plan_service.generate_trip_itinerary(plan_id, data, actor_id, actor_role)

    def preview_trip_itinerary(
        self,
        plan_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        return self.trip_plan_service.preview_trip_itinerary(plan_id, data, actor_id, actor_role)

    def get_trip_transport_suggestions(
        self,
        plan_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
        *,
        force_refresh: bool = False,
    ) -> Optional[dict]:
        return self.trip_plan_service.get_trip_transport_suggestions(
            plan_id,
            data,
            actor_id,
            actor_role,
            force_refresh=force_refresh,
        )

    def archive_trip_stop(
        self,
        plan_id: str,
        stop_id: str,
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> Optional[dict]:
        return self.trip_plan_service.archive_trip_stop(plan_id, stop_id, actor_id, actor_role, row_version)

    def add_trip_free_stop(
        self, plan_id: str, data: dict, actor_id: str, actor_role: str
    ) -> Optional[dict]:
        return self.trip_plan_service.add_trip_free_stop(
            plan_id, data, actor_id, actor_role
        )

    def update_trip_free_stop(
        self,
        plan_id: str,
        free_stop_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        return self.trip_plan_service.update_trip_free_stop(
            plan_id, free_stop_id, data, actor_id, actor_role
        )

    def archive_trip_free_stop(
        self,
        plan_id: str,
        free_stop_id: str,
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> Optional[dict]:
        return self.trip_plan_service.archive_trip_free_stop(
            plan_id, free_stop_id, actor_id, actor_role, row_version
        )

    def export_trip_plan_markdown(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[str]:
        return self.trip_plan_service.export_trip_plan_markdown(plan_id, actor_id, actor_role)

    def export_trip_plan_csv(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[str]:
        return self.trip_plan_service.export_trip_plan_csv(plan_id, actor_id, actor_role)

    def export_trip_plan_xlsx(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[bytes]:
        return self.trip_plan_service.export_trip_plan_xlsx(plan_id, actor_id, actor_role)

    def export_trip_plan_html(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[bytes]:
        return self.trip_plan_service.export_trip_plan_html(plan_id, actor_id, actor_role)

    def export_trip_plan_ics(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[bytes]:
        return self.trip_plan_service.export_trip_plan_ics(plan_id, actor_id, actor_role)

    def get_trip_execution(
        self,
        plan_id: str,
        actor_id: str,
        actor_role: str,
        visit_date: Optional[str] = None,
    ) -> Optional[dict]:
        return self.trip_plan_service.get_trip_execution(plan_id, actor_id, actor_role, visit_date)

    def export_trip_execution_markdown(
        self,
        plan_id: str,
        actor_id: str,
        actor_role: str,
        visit_date: Optional[str] = None,
    ) -> Optional[str]:
        return self.trip_plan_service.export_trip_execution_markdown(plan_id, actor_id, actor_role, visit_date)

    def _visible_lead_rows(self, actor_id: str, actor_role: str, filters: dict) -> list[dict]:
        """Load visible leads with customer and owner fields."""
        return self.visibility_service.visible_lead_rows(actor_id, actor_role, filters)

    def _visible_lead_by_id(self, lead_id: str, actor_id: str, actor_role: str) -> Optional[dict]:
        return self.visibility_service.visible_lead_by_id(lead_id, actor_id, actor_role)

    def _can_access_customer(self, customer_id: str, actor_id: str, actor_role: str) -> bool:
        return self.visibility_service.can_access_customer(customer_id, actor_id, actor_role)

    def _activity_stats(self, lead_ids: list[str]) -> dict[str, dict]:
        if not lead_ids:
            return {}
        placeholders = ", ".join("?" * len(lead_ids))
        rows = self.activity_repo.conn.execute(
            f"""
            SELECT
                lead_id,
                COUNT(*) AS activity_count,
                SUM(CASE WHEN action_type = 'follow_up' THEN 1 ELSE 0 END) AS follow_up_count,
                MAX(created_at) AS last_activity_at
            FROM lead_activities
            WHERE archived_at IS NULL
              AND lead_id IN ({placeholders})
            GROUP BY lead_id
            """,
            lead_ids,
        ).fetchall()
        return {row["lead_id"]: dict(row) for row in rows}

    def _stage_breakdown(self, leads: list[dict]) -> list[dict]:
        order = ["New", "Assigned", "Following", "Quoted", "Won", "Lost"]
        grouped = {stage: {"stage": stage, "count": 0, "value": 0.0} for stage in order}
        for lead in leads:
            stage = lead.get("sales_stage") or "Unknown"
            item = grouped.setdefault(stage, {"stage": stage, "count": 0, "value": 0.0})
            item["count"] += 1
            item["value"] += self._num(lead.get("deal_amount")) or self._num(lead.get("estimated_value"))
        return [grouped[stage] for stage in order if grouped.get(stage, {}).get("count")]

    def _group_performance(self, leads: list[dict], key: str, default: str) -> list[dict]:
        grouped: dict[str, dict] = {}
        for lead in leads:
            label = lead.get(key) or default
            item = grouped.setdefault(
                label,
                {
                    "label": label,
                    "total": 0,
                    "open": 0,
                    "won": 0,
                    "lost": 0,
                    "pipeline_value": 0.0,
                    "won_value": 0.0,
                    "follow_ups": 0,
                },
            )
            item["total"] += 1
            item["follow_ups"] += int(lead.get("follow_up_count") or 0)
            stage = lead.get("sales_stage")
            if stage == "Won":
                item["won"] += 1
                item["won_value"] += self._num(lead.get("deal_amount"))
            elif stage == "Lost":
                item["lost"] += 1
            else:
                item["open"] += 1
                item["pipeline_value"] += self._num(lead.get("estimated_value"))

        result = []
        for item in grouped.values():
            closed = item["won"] + item["lost"]
            item["win_rate"] = item["won"] / closed if closed else 0
            item["average_followups"] = item["follow_ups"] / item["total"] if item["total"] else 0
            result.append(item)
        result.sort(key=lambda row: (row["won_value"], row["pipeline_value"], row["total"]), reverse=True)
        return result[:20]

    def _lost_reason_breakdown(self, lost_leads: list[dict]) -> list[dict]:
        counts: defaultdict[str, int] = defaultdict(int)
        for lead in lost_leads:
            reason = lead.get("lost_reason_code") or lead.get("lost_reason_text") or "Unspecified"
            counts[reason] += 1
        return [
            {"reason": reason, "count": count}
            for reason, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]

    def _risk_leads(self, open_leads: list[dict], limit: int = 10) -> list[dict]:
        today = date.today()
        items = []
        for lead in open_leads:
            score = 0
            reasons = []
            value = self._num(lead.get("estimated_value")) or self._num(lead.get("deal_amount"))
            next_followup = lead.get("next_followup_date")
            if next_followup and str(next_followup) < today.isoformat():
                score += RISK_SCORE_WEIGHTS["overdue_followup"]
                reasons.append("Overdue follow-up")
            if (lead.get("days_since_activity") or 0) >= 30:
                score += RISK_SCORE_WEIGHTS["stale_activity"]
                reasons.append("No activity for 30+ days")
            if value >= 50000:
                score += RISK_SCORE_WEIGHTS["high_value"]
                reasons.append("High value")
            if lead.get("sales_stage") == "Quoted":
                score += RISK_SCORE_WEIGHTS["quoted"]
                reasons.append("Quoted but not won")
            if score:
                items.append({**self._lead_summary(lead), "risk_score": score, "risk_reasons": reasons})
        items.sort(key=lambda item: (item["risk_score"], item["value"]), reverse=True)
        return items[:limit]

    def _high_value_open_leads(self, open_leads: list[dict], limit: int = 10) -> list[dict]:
        items = [self._lead_summary(lead) for lead in open_leads]
        items.sort(key=lambda item: item["value"], reverse=True)
        return [item for item in items if item["value"] > 0][:limit]

    def _lead_summary(self, lead: dict) -> dict:
        return {
            "id": lead.get("id"),
            "display_id": lead.get("display_id"),
            "title": lead.get("title"),
            "customer_id": lead.get("customer_id"),
            "customer_name": lead.get("customer_name"),
            "country": lead.get("country"),
            "city": lead.get("city"),
            "owner_name": lead.get("owner_name"),
            "stage": lead.get("sales_stage"),
            "value": self._num(lead.get("deal_amount")) or self._num(lead.get("estimated_value")),
            "next_followup_date": lead.get("next_followup_date"),
            "days_since_activity": lead.get("days_since_activity"),
        }

    def _analysis_brief(self, summary: dict) -> str:
        return (
            f"{summary['total_leads']} leads reviewed, including "
            f"{summary['open_leads']} open, {summary['won_leads']} won, "
            f"and {summary['lost_leads']} lost. Pipeline value is "
            f"{summary['pipeline_value']:,.0f}; won value is {summary['won_value']:,.0f}. "
            f"{summary['overdue_followups']} leads have overdue follow-ups and "
            f"{summary['stale_open_leads']} open leads have no activity for 30+ days."
        )

    def _trip_candidate_from_point(self, point: dict, missing_location: bool) -> dict:
        leads = point.get("leads") or []
        open_leads = [lead for lead in leads if lead.get("sales_stage") not in {"Won", "Lost"}]
        quoted = [lead for lead in leads if lead.get("sales_stage") == "Quoted"]
        following = [lead for lead in leads if lead.get("sales_stage") == "Following"]
        service = [lead for lead in leads if lead.get("service_status") not in {None, "None", ""}]
        pipeline_value = sum(self._num(lead.get("estimated_value")) for lead in open_leads)
        won_value = sum(self._num(lead.get("deal_amount")) for lead in leads if lead.get("sales_stage") == "Won")

        score = (
            len(open_leads) * TRIP_SCORE_WEIGHTS["open_lead"]
            + len(quoted) * TRIP_SCORE_WEIGHTS["quoted"]
            + len(following) * TRIP_SCORE_WEIGHTS["following"]
            + min(
                pipeline_value / TRIP_SCORE_WEIGHTS["pipeline_value_divisor"],
                TRIP_SCORE_WEIGHTS["pipeline_value_cap"],
            )
        )
        reasons = []
        if len(open_leads) > 1:
            reasons.append("Multiple open leads")
        if quoted:
            reasons.append("Quoted opportunities")
        if following:
            reasons.append("Active follow-up")
        if pipeline_value:
            reasons.append("Pipeline value")
        if service:
            score += TRIP_SCORE_WEIGHTS["service_context"]
            reasons.append("Service or renewal context")
        if point.get("needs_geocode") or missing_location:
            score -= TRIP_SCORE_WEIGHTS["coordinate_review_penalty"]
            reasons.append("Coordinate needs review")

        primary = sorted(
            leads,
            key=lambda lead: (
                lead.get("sales_stage") == "Quoted",
                self._num(lead.get("estimated_value")) or self._num(lead.get("deal_amount")),
                lead.get("updated_at") or "",
            ),
            reverse=True,
        )[0] if leads else {}

        return {
            "customer_id": point.get("customer_id"),
            "customer_name": point.get("customer_name"),
            "city": point.get("city"),
            "country": point.get("country_name") or point.get("country"),
            "region": point.get("region"),
            "lat": point.get("lat"),
            "lng": point.get("lng"),
            "coordinate_quality": point.get("coordinate_quality"),
            "needs_coordinate_review": bool(point.get("needs_geocode") or missing_location),
            "lead_count": point.get("lead_count") or len(leads),
            "open_count": len(open_leads),
            "won_count": point.get("won_count") or 0,
            "pipeline_value": pipeline_value,
            "won_value": won_value,
            "score": round(score, 1),
            "reasons": reasons,
            "primary_lead_id": primary.get("id"),
            "primary_lead_display_id": primary.get("display_id"),
            "primary_stage": primary.get("sales_stage"),
            "owners": point.get("owners") or [],
            "leads": leads[:6],
        }

    def _trip_candidate_from_missing(self, item: dict) -> dict:
        return {
            "customer_id": item.get("customer_id"),
            "customer_name": item.get("customer_name"),
            "city": item.get("city"),
            "country": item.get("country"),
            "region": item.get("region"),
            "lat": None,
            "lng": None,
            "coordinate_quality": "missing",
            "needs_coordinate_review": True,
            "lead_count": item.get("lead_count") or 0,
            "open_count": item.get("lead_count") or 0,
            "won_count": 0,
            "pipeline_value": 0,
            "won_value": 0,
            "score": max(1, (item.get("lead_count") or 0) * 10 - 8),
            "reasons": ["Missing coordinates"],
            "primary_lead_id": item.get("latest_lead_id"),
            "primary_lead_display_id": None,
            "primary_stage": None,
            "owners": [],
            "leads": [],
        }

    WAYPOINT_CATEGORIES = frozenset({"airport", "transit"})

    def _calculate_trip_itinerary(self, plan: dict, data: dict) -> dict:
        stops = plan.get("stops") or []
        if not stops:
            raise ValueError("Add at least one stop before generating an itinerary")

        window_keys = (
            "departure_window_start",
            "departure_window_end",
            "return_window_start",
            "return_window_end",
        )
        windows = {
            key: data[key] if key in data else plan.get(key)
            for key in window_keys
        }
        validate_time_windows(windows)
        start_value = (
            data.get("start_date")
            or plan.get("start_date")
            or windows.get("departure_window_start")
        )
        start = self._parse_date(start_value)
        if not start:
            raise ValueError("start_date is required before generating an itinerary")

        requested_end_value = (
            data.get("end_date") if "end_date" in data else plan.get("end_date")
        )
        if not requested_end_value:
            requested_end_value = windows.get("return_window_end")
        requested_end = self._parse_date(requested_end_value)
        if requested_end_value and not requested_end:
            raise ValueError("end_date must be a valid ISO date")
        if requested_end and requested_end < start:
            raise ValueError("end_date cannot be before start_date")
        departure_start_slot = self._window_slot(
            windows.get("departure_window_start"), default_period="AM"
        )
        departure_end_slot = self._window_slot(
            windows.get("departure_window_end"), default_period="PM"
        )
        return_start_slot = self._window_slot(
            windows.get("return_window_start"), default_period="AM"
        )
        return_end_slot = self._window_slot(
            windows.get("return_window_end"), default_period="PM"
        )

        travel_mode = data.get("travel_mode") or plan.get("travel_mode") or "auto"
        if travel_mode not in TRIP_TRAVEL_MODES:
            raise ValueError("Unsupported travel mode")
        if "transport_mode_priority" in data:
            priority = normalize_priority(data.get("transport_mode_priority"), travel_mode)
        elif "travel_mode" in data:
            priority = normalize_priority(None, travel_mode)
        else:
            priority = normalize_priority(plan.get("transport_mode_priority"), travel_mode)
        route_order_mode = validate_route_order_mode(
            data.get("route_order_mode") or plan.get("route_order_mode")
        )
        avoid_weekends = data.get("avoid_weekends")
        if avoid_weekends is None:
            avoid_weekends = bool(plan.get("avoid_weekends", True))
        holiday_input = data.get("holiday_dates") if "holiday_dates" in data else plan.get("holiday_dates")
        holidays, invalid_holidays = self._parse_holiday_dates(holiday_input)
        warnings = []
        if invalid_holidays:
            warnings.append(
                "Ignored invalid holiday dates: " + ", ".join(invalid_holidays[:5])
            )

        routable_stops = []
        missing_locations = []
        for stop in stops:
            point = self._route_point_from_stop(stop)
            if not point:
                missing_locations.append(
                    stop.get("location_name")
                    or stop.get("customer_name")
                    or stop.get("customer_id")
                    or stop.get("id")
                )
                continue
            routable_stops.append(
                (
                    stop,
                    {
                        **point,
                        "kind": "stop",
                        "stop_id": stop["id"],
                        "stop_kind": stop.get("stop_kind") or "customer",
                    },
                )
            )
        if missing_locations:
            raise ValueError("Stops need latitude and longitude: " + ", ".join(missing_locations[:5]))

        stop_durations = self._clean_stop_durations(
            data, {str(stop["id"]) for stop in stops}
        )
        origin_data = self._route_endpoint("origin", data, plan)
        if not origin_data:
            raise ValueError(
                "Set the trip departure location and its coordinates before previewing the route"
            )
        destination_data = self._route_endpoint("destination", data, plan)
        if not destination_data:
            raise ValueError(
                "Set the trip return location and its coordinates before previewing the route"
            )
        origin = {**origin_data, "kind": "origin", "stop_id": None}
        destination = {**destination_data, "kind": "destination", "stop_id": None}
        explicit_order = validate_stop_order(
            data.get("stop_order") if "stop_order" in data else None,
            [stop["id"] for stop in stops],
        )
        if explicit_order:
            by_id = {stop["id"]: (stop, point) for stop, point in routable_stops}
            ordered_stops = [by_id[stop_id] for stop_id in explicit_order]
            route_order_mode = "manual"
        elif route_order_mode == "manual":
            ordered_stops = routable_stops
        else:
            ordered_stops = self._order_route_stops(
                origin, destination, routable_stops, priority
            )

        incoming_overrides = (
            data.get("leg_overrides") if "leg_overrides" in data else None
        )
        # Transport is chosen per stop-to-stop connection. Decide the modes on a
        # route without airports, then let only the flown legs route through one:
        # driving to an airport just to drive on to the next stop is nonsense.
        base_stops, waypoint_groups = split_waypoints(ordered_stops)
        if waypoint_groups:
            base_points = [origin, *[point for _, point in base_stops], destination]
            flown = flight_leg_indices(
                base_points,
                priority,
                {
                    **self._shared_leg_settings(plan["id"]),
                    **(incoming_overrides if isinstance(incoming_overrides, dict) else {}),
                },
                lambda start, end: self._haversine_km(
                    start["lat"], start["lng"], end["lat"], end["lng"]
                ),
            )
            ordered_stops = apply_flight_waypoints(base_stops, waypoint_groups, flown)

        route_points = [origin, *[point for _, point in ordered_stops], destination]
        leg_keys = {
            f"{left.get('stop_id') or 'origin'}>{right.get('stop_id') or 'destination'}"
            for left, right in zip(route_points, route_points[1:])
        }
        if route_order_mode == "auto" and isinstance(incoming_overrides, dict):
            obsolete_keys = sorted(set(incoming_overrides) - leg_keys)
            if obsolete_keys:
                incoming_overrides = {
                    key: value
                    for key, value in incoming_overrides.items()
                    if key in leg_keys
                }
                warnings.append(
                    "Ignored obsolete leg overrides after automatic route reorder: "
                    + ", ".join(obsolete_keys)
                )
        stored = self._shared_leg_settings(plan["id"])
        dropped_airports = sorted(
            leg_key
            for (member_id, leg_key) in self.trip_plan_service.leg_repo.saved_airports(
                plan["id"]
            )
            if member_id is None and leg_key not in leg_keys
        )
        if dropped_airports:
            warnings.append(
                "These legs no longer exist after reordering, so their airports "
                "are not used: " + ", ".join(dropped_airports)
            )
        overrides = normalize_overrides(incoming_overrides, leg_keys, stored)

        current_point = origin
        initial_slot = departure_start_slot or (start, "AM")
        # Leaving on a Saturday to meet a customer on Monday is ordinary. Only
        # the customer visit needs a working day, so the trip starts when the
        # traveller says it does.
        cursor = initial_slot
        total_distance = 0.0
        total_hours = 0.0
        total_travel_half_days = 0
        stop_updates = []
        risks: list[dict] = []
        legs = []
        schedule_items = []
        last_occupied_slot = cursor

        def append_schedule_items(
            slots: list[tuple[date, str]],
            *,
            item_type: str,
            source_id: str,
            sequence_no: int,
            title: str,
            confirmation_status: str | None,
            details: Optional[dict] = None,
        ) -> None:
            for half_index, slot in enumerate(slots, start=1):
                schedule_items.append(
                    {
                        "slot_key": f"{slot[0].isoformat()}:{slot[1]}",
                        "date": slot[0].isoformat(),
                        "period": slot[1],
                        "item_type": item_type,
                        "source_id": source_id,
                        "sequence_no": sequence_no,
                        "title": title,
                        "half_day_index": half_index,
                        "half_day_count": len(slots),
                        "confirmation_status": confirmation_status,
                        **(details or {}),
                    }
                )

        for sequence_no, (stop, point) in enumerate(ordered_stops, start=1):
            key = f"{current_point.get('stop_id') or 'origin'}>{point['stop_id']}"
            leg = build_leg(
                self, sequence_no, current_point, point, priority, overrides.get(key)
            )
            leg["plan_id"] = plan["id"]
            segments = self._expand_flight_leg(leg, current_point, point, priority)
            leg_slots = []
            if segments:
                # One stored connection, several real movements: the transfers to
                # and from the airport and any wait between them all take time.
                for index, segment in enumerate(segments, start=1):
                    slots, cursor = self._allocate_calendar_slots(
                        cursor, segment["travel_half_days"]
                    )
                    segment["planned_start_date"] = (
                        slots[0][0].isoformat() if slots else None
                    )
                    segment["planned_start_period"] = slots[0][1] if slots else None
                    segment["planned_end_date"] = (
                        slots[-1][0].isoformat() if slots else None
                    )
                    segment["planned_end_period"] = slots[-1][1] if slots else None
                    leg_slots.extend(slots)
                    append_schedule_items(
                        slots,
                        item_type="leg",
                        source_id=f"{leg['leg_key']}#{index}",
                        sequence_no=sequence_no,
                        title=(
                            f"{segment.get('from_label') or '-'} → "
                            f"{segment.get('to_label') or '-'}"
                        ),
                        confirmation_status=None,
                        details={
                            "selected_mode": segment["selected_mode"],
                            "distance_km": segment["distance_km"],
                            "time_hours": segment["time_hours"],
                            "segment_role": segment["role"],
                        },
                    )
                    if segment["stay_half_days"]:
                        stay_slots, cursor = self._allocate_calendar_slots(
                            cursor, segment["stay_half_days"]
                        )
                        leg_slots.extend(stay_slots)
                        append_schedule_items(
                            stay_slots,
                            item_type="airport",
                            source_id=f"{leg['leg_key']}#{index}-stay",
                            sequence_no=sequence_no,
                            title=segment.get("stay_label") or "Airport",
                            confirmation_status=None,
                            details={"segment_role": f"{segment['role']}_stay"},
                        )
                leg["segments"] = segments
                leg["distance_km"] = round(
                    sum(item["distance_km"] for item in segments), 1
                )
                leg["time_hours"] = round(
                    sum(item["time_hours"] for item in segments), 1
                )
                leg["travel_half_days"] = min(60, len(leg_slots))
                leg["travel_days"] = math.ceil(leg["travel_half_days"] / 2)
            else:
                leg_slots, cursor = self._allocate_calendar_slots(
                    cursor, int(leg["travel_half_days"])
                )
                append_schedule_items(
                    leg_slots,
                    item_type="leg",
                    source_id=leg["leg_key"],
                    sequence_no=sequence_no,
                    title=(
                        f"{leg.get('from_label') or '-'} → "
                        f"{leg.get('to_label') or '-'}"
                    ),
                    confirmation_status=None,
                    details={
                        "selected_mode": leg.get("selected_mode"),
                        "distance_km": leg.get("distance_km"),
                        "time_hours": leg.get("time_hours"),
                    },
                )
            travel_half_days = int(leg["travel_half_days"])
            leg["planned_start_date"] = (
                leg_slots[0][0].isoformat() if leg_slots else None
            )
            leg["planned_start_period"] = leg_slots[0][1] if leg_slots else None
            leg["planned_end_date"] = (
                leg_slots[-1][0].isoformat() if leg_slots else None
            )
            leg["planned_end_period"] = leg_slots[-1][1] if leg_slots else None
            legs.append(leg)
            if leg_slots:
                last_occupied_slot = leg_slots[-1]
            if (
                sequence_no == 1
                and departure_end_slot
                and leg_slots
                and self._slot_key(leg_slots[-1])
                > self._slot_key(departure_end_slot)
            ):
                warnings.append(
                    "The outbound leg exceeds the selected departure window."
                )

            override = stop_durations.get(stop["id"], {})
            duration_half_days = self._clean_half_days(
                override.get(
                    "half_days",
                    stop.get("duration_half_days")
                    or self._clean_stay_days(stop.get("stay_days")) * 2,
                ),
                f"duration_half_days[{stop['id']}]",
            )
            preferred_period = override.get(
                "preferred_period", stop.get("preferred_period") or "auto"
            )
            if preferred_period not in {"auto", "AM", "PM"}:
                raise ValueError("Visit time preference must be Automatic, AM, or PM")
            schedule_locked = bool(
                override.get("locked", bool(stop.get("schedule_locked")))
            )
            if schedule_locked and route_order_mode != "manual":
                raise ValueError(
                    "Set the route order to manual before locking a visit time"
                )

            is_customer = (stop.get("stop_kind") or "customer") != "free"
            is_waypoint = (
                not is_customer
                and stop.get("category") in self.WAYPOINT_CATEGORIES
            )
            # Only customer visits need business hours; travel, hotels and rests
            # happen on the calendar, and airports are passed through.
            schedule_half_days = 0 if is_waypoint else duration_half_days
            visit_start_slot = self._seek_preferred_period(
                cursor,
                preferred_period,
                bool(avoid_weekends),
                holidays,
                calendar_only=not is_customer,
            )
            if schedule_locked:
                locked_date = self._parse_date(stop.get("planned_date"))
                locked_period = stop.get("planned_start_period")
                if not locked_date or locked_period not in {"AM", "PM"}:
                    raise ValueError(
                        "Save a visit date and AM/PM period before locking this visit"
                    )
                locked_slot = (locked_date, locked_period)
                # A confirmed appointment is a fact, not a preference. Skipping
                # weekends and holidays is how the planner arranges the visits it
                # is free to move, and holiday_dates are Chinese dates that say
                # nothing about when an overseas customer is at work.
                if not self._is_workday(
                    locked_date, bool(avoid_weekends), holidays
                ):
                    # The message is emitted as a key plus its values so the
                    # frontend can localise it; a pre-formatted sentence with the
                    # date already inside can never be matched for translation.
                    risks.append(
                        {
                            "kind": "booked_on_skipped_day",
                            "stop_id": stop["id"],
                            "date": locked_date.isoformat(),
                        }
                    )
                if preferred_period != "auto" and preferred_period != locked_period:
                    raise ValueError(
                        "The locked visit time conflicts with its AM/PM preference"
                    )
                if self._slot_key(locked_slot) < self._slot_key(visit_start_slot):
                    raise ValueError(
                        "The route cannot reach this visit before its locked time"
                    )
                visit_start_slot = locked_slot

            if is_customer and not schedule_locked:
                visit_slots, cursor = self._allocate_work_slots(
                    visit_start_slot,
                    schedule_half_days,
                    bool(avoid_weekends),
                    holidays,
                )
            elif is_customer:
                # Allocating work slots here would quietly move a Saturday
                # appointment to Monday and undo the booking that was kept.
                visit_slots, cursor = self._allocate_calendar_slots(
                    visit_start_slot, schedule_half_days
                )
            else:
                visit_slots, cursor = self._allocate_calendar_slots(
                    visit_start_slot, schedule_half_days
                )
            visit_start = visit_slots[0] if visit_slots else visit_start_slot
            visit_end = visit_slots[-1] if visit_slots else visit_start_slot
            stay_days = math.ceil(duration_half_days / 2)
            confirmation_status = stop.get("confirmation_status") or "unconfirmed"
            schedule_semantic_changed = any(
                (
                    stop.get("sequence_no") != sequence_no,
                    stop.get("planned_date") != visit_start[0].isoformat(),
                    stop.get("planned_end_date") != visit_end[0].isoformat(),
                    stop.get("planned_start_period") != visit_start[1],
                    stop.get("planned_end_period") != visit_end[1],
                    int(stop.get("duration_half_days") or 0) != duration_half_days,
                    (stop.get("preferred_period") or "auto") != preferred_period,
                    bool(stop.get("schedule_locked")) != schedule_locked,
                )
            )
            if confirmation_status == "confirmed" and schedule_semantic_changed:
                confirmation_status = "needs_reconfirmation"
            stop_updates.append(
                {
                    "id": stop["id"],
                    "stop_kind": stop.get("stop_kind") or "customer",
                    "sequence_no": sequence_no,
                    "planned_date": visit_start[0].isoformat(),
                    "planned_end_date": visit_end[0].isoformat(),
                    "planned_start_period": visit_start[1],
                    "planned_end_period": visit_end[1],
                    "duration_half_days": duration_half_days,
                    "schedule_half_days": schedule_half_days,
                    "stay_days": stay_days,
                    "preferred_period": preferred_period,
                    "schedule_locked": schedule_locked,
                    "confirmation_status": confirmation_status,
                    "travel_from_label": leg["from_label"],
                    "travel_mode": leg["selected_mode"],
                    "travel_distance_km": leg["distance_km"],
                    "travel_time_hours": leg["time_hours"],
                    "travel_days": int(leg["travel_days"]),
                }
            )
            # A waypoint occupies no time but still has to appear on the timeline.
            append_schedule_items(
                visit_slots or [visit_start_slot],
                item_type=(stop.get("stop_kind") or "customer"),
                source_id=stop["id"],
                sequence_no=sequence_no,
                title=(
                    stop.get("location_name")
                    or stop.get("customer_name")
                    or "Stop"
                ),
                confirmation_status=confirmation_status,
                details={"waypoint": True} if is_waypoint else None,
            )

            total_distance += leg["distance_km"]
            total_hours += leg["time_hours"]
            total_travel_half_days += travel_half_days
            current_point = point
            last_occupied_slot = visit_end

        final_key = f"{current_point.get('stop_id') or 'origin'}>destination"
        final_leg = build_leg(
            self,
            len(ordered_stops) + 1,
            current_point,
            destination,
            priority,
            overrides.get(final_key),
        )
        final_leg["plan_id"] = plan["id"]
        final_half_days = int(final_leg["travel_half_days"])
        if (
            return_start_slot
            and self._slot_key(return_start_slot) > self._slot_key(cursor)
        ):
            cursor = return_start_slot
        final_sequence = len(ordered_stops) + 1
        final_segments = self._expand_flight_leg(
            final_leg, current_point, destination, priority
        )
        final_slots = []
        if final_segments:
            for index, segment in enumerate(final_segments, start=1):
                slots, cursor = self._allocate_calendar_slots(
                    cursor, segment["travel_half_days"]
                )
                segment["planned_start_date"] = (
                    slots[0][0].isoformat() if slots else None
                )
                segment["planned_start_period"] = slots[0][1] if slots else None
                segment["planned_end_date"] = (
                    slots[-1][0].isoformat() if slots else None
                )
                segment["planned_end_period"] = slots[-1][1] if slots else None
                final_slots.extend(slots)
                append_schedule_items(
                    slots,
                    item_type="leg",
                    source_id=f"{final_leg['leg_key']}#{index}",
                    sequence_no=final_sequence,
                    title=(
                        f"{segment.get('from_label') or '-'} → "
                        f"{segment.get('to_label') or '-'}"
                    ),
                    confirmation_status=None,
                    details={
                        "selected_mode": segment["selected_mode"],
                        "distance_km": segment["distance_km"],
                        "time_hours": segment["time_hours"],
                        "segment_role": segment["role"],
                    },
                )
                if segment["stay_half_days"]:
                    stay_slots, cursor = self._allocate_calendar_slots(
                        cursor, segment["stay_half_days"]
                    )
                    final_slots.extend(stay_slots)
                    append_schedule_items(
                        stay_slots,
                        item_type="airport",
                        source_id=f"{final_leg['leg_key']}#{index}-stay",
                        sequence_no=final_sequence,
                        title=segment.get("stay_label") or "Airport",
                        confirmation_status=None,
                        details={"segment_role": f"{segment['role']}_stay"},
                    )
            final_leg["segments"] = final_segments
            final_leg["distance_km"] = round(
                sum(item["distance_km"] for item in final_segments), 1
            )
            final_leg["time_hours"] = round(
                sum(item["time_hours"] for item in final_segments), 1
            )
            final_leg["travel_half_days"] = min(60, len(final_slots))
            final_leg["travel_days"] = math.ceil(final_leg["travel_half_days"] / 2)
            final_half_days = int(final_leg["travel_half_days"])
        else:
            final_slots, cursor = self._allocate_calendar_slots(cursor, final_half_days)
            append_schedule_items(
                final_slots,
                item_type="leg",
                source_id=final_leg["leg_key"],
                sequence_no=final_sequence,
                title=(
                    f"{final_leg.get('from_label') or '-'} → "
                    f"{final_leg.get('to_label') or '-'}"
                ),
                confirmation_status=None,
                details={
                    "selected_mode": final_leg.get("selected_mode"),
                    "distance_km": final_leg.get("distance_km"),
                    "time_hours": final_leg.get("time_hours"),
                },
            )
        final_leg["planned_start_date"] = (
            final_slots[0][0].isoformat() if final_slots else None
        )
        final_leg["planned_start_period"] = final_slots[0][1] if final_slots else None
        final_leg["planned_end_date"] = (
            final_slots[-1][0].isoformat() if final_slots else None
        )
        final_leg["planned_end_period"] = final_slots[-1][1] if final_slots else None
        legs.append(final_leg)
        if final_slots:
            last_occupied_slot = final_slots[-1]
        calculated_end = last_occupied_slot[0]
        calculated_end_period = last_occupied_slot[1]
        total_distance += final_leg["distance_km"]
        total_hours += final_leg["time_hours"]
        total_travel_half_days += final_half_days

        boundary_candidates = []
        if requested_end:
            boundary_candidates.append((requested_end, "PM"))
        if return_end_slot:
            boundary_candidates.append(return_end_slot)
        requested_boundary = (
            min(boundary_candidates, key=self._slot_key)
            if boundary_candidates else None
        )
        overrun_half_days = (
            self._calendar_slots_after(requested_boundary, last_occupied_slot)
            if requested_boundary
            else 0
        )
        overrun_days = overrun_half_days / 2
        within_date_window = requested_boundary is None or overrun_half_days == 0
        if not within_date_window:
            warnings.append(
                "Itinerary exceeds requested end date "
                f"{requested_boundary[0].isoformat()} {requested_boundary[1]} "
                f"by {overrun_half_days} half-day slot(s)."
            )

        schedule_items.sort(
            key=lambda item: (
                item["date"],
                0 if item["period"] == "AM" else 1,
                item["sequence_no"],
                0 if item["item_type"] == "leg" else 1,
            )
        )
        for schedule_index, item in enumerate(schedule_items, start=1):
            item["schedule_index"] = schedule_index

        summary = {
            "generated_at": now_iso(),
            "start_date": start.isoformat(),
            "calculated_end_date": calculated_end.isoformat(),
            "calculated_end_period": calculated_end_period,
            "requested_end_date": (
                requested_boundary[0].isoformat() if requested_boundary else None
            ),
            "requested_end_period": (
                requested_boundary[1] if requested_boundary else None
            ),
            "overrun_days": overrun_days,
            "overrun_half_days": overrun_half_days,
            "within_date_window": within_date_window,
            "risks": risks,
            "stop_count": len(ordered_stops),
            "leg_count": len(legs),
            "total_stay_half_days": sum(
                item["schedule_half_days"] for item in stop_updates
            ),
            "total_stay_days": sum(
                item["schedule_half_days"] for item in stop_updates
            ) / 2,
            "total_travel_half_days": total_travel_half_days,
            "total_travel_days": total_travel_half_days / 2,
            "total_schedule_half_days": len(schedule_items),
            "total_business_days": self._business_days_between(start, calculated_end, avoid_weekends, holidays),
            "total_calendar_days": (calculated_end - start).days + 1,
            "total_distance_km": round(total_distance, 1),
            "total_travel_hours": round(total_hours, 1),
            "travel_mode": travel_mode,
            "route_order_mode": route_order_mode,
            "transport_mode_priority": priority,
            **windows,
            "avoid_weekends": bool(avoid_weekends),
            "holiday_dates": holidays,
            "warnings": warnings,
            "final_leg": final_leg,
            "schedule_items": schedule_items,
        }
        plan_updates = self._prepare_trip_plan_data(
            {
                **data,
                "start_date": start.isoformat(),
                "end_date": (
                    requested_end.isoformat()
                    if requested_end
                    else calculated_end.isoformat()
                ),
                "travel_mode": travel_mode,
                "route_order_mode": route_order_mode,
                "transport_mode_priority": priority,
                **windows,
                "avoid_weekends": bool(avoid_weekends),
                "holiday_dates": holidays,
                "itinerary_generated_at": summary["generated_at"],
                "itinerary_summary": summary,
            },
            include_system_fields=True,
        )
        return {
            "summary": summary,
            "stop_updates": stop_updates,
            "legs": legs,
            "plan_updates": plan_updates,
        }

    def _trip_itinerary_preview_plan(self, plan: dict, calculation: dict) -> dict:
        preview = {**plan}
        summary = calculation["summary"]
        preview.update(
            {
                "start_date": summary["start_date"],
                "end_date": summary.get("requested_end_date") or summary["calculated_end_date"],
                "requested_end_date": summary.get("requested_end_date"),
                "overrun_days": summary.get("overrun_days", 0),
                "within_date_window": summary.get("within_date_window", True),
                "travel_mode": summary["travel_mode"],
                "route_order_mode": summary["route_order_mode"],
                "transport_mode_priority": summary["transport_mode_priority"],
                "avoid_weekends": summary["avoid_weekends"],
                "holiday_dates": summary["holiday_dates"],
                "departure_window_start": summary.get("departure_window_start"),
                "departure_window_end": summary.get("departure_window_end"),
                "return_window_start": summary.get("return_window_start"),
                "return_window_end": summary.get("return_window_end"),
                "itinerary_generated_at": summary["generated_at"],
                "itinerary_summary": {**summary, "preview": True},
                "itinerary_preview": True,
            }
        )
        stop_updates = {item["id"]: item for item in calculation["stop_updates"]}
        preview["stops"] = sorted(
            [
                {**stop, **stop_updates.get(stop["id"], {})}
                for stop in plan.get("stops", [])
            ],
            key=lambda item: (item.get("sequence_no") or 0, item.get("created_at") or ""),
        )
        preview["legs"] = calculation["legs"]
        preview["schedule_items"] = list(summary.get("schedule_items") or [])
        return preview

    def _normalize_trip_plan_row(self, row: dict) -> dict:
        row["avoid_weekends"] = bool(row.get("avoid_weekends", 1))
        row["holiday_dates"] = self._clean_holiday_dates(row.get("holiday_dates"))
        try:
            row["transport_mode_priority"] = normalize_priority(
                row.get("transport_mode_priority"), row.get("travel_mode")
            )
        except ValueError:
            row["transport_mode_priority"] = normalize_priority(
                None, row.get("travel_mode")
            )
        try:
            row["route_order_mode"] = validate_route_order_mode(
                row.get("route_order_mode")
            )
        except ValueError:
            row["route_order_mode"] = "auto"
        summary = row.get("itinerary_summary")
        if isinstance(summary, str) and summary:
            try:
                row["itinerary_summary"] = json.loads(summary)
            except json.JSONDecodeError:
                row["itinerary_summary"] = None
        return row

    def _prepare_trip_plan_data(self, data: dict, include_system_fields: bool = False) -> dict:
        allowed = {
            "title",
            "owner_id",
            "start_date",
            "end_date",
            "region",
            "description",
            "status",
            "origin_name",
            "origin_lat",
            "origin_lng",
            "destination_name",
            "destination_lat",
            "destination_lng",
            "travel_mode",
            "route_order_mode",
            "transport_mode_priority",
            "departure_window_start",
            "departure_window_end",
            "return_window_start",
            "return_window_end",
            "avoid_weekends",
            "holiday_dates",
        }
        if include_system_fields:
            allowed.update({"itinerary_generated_at", "itinerary_summary"})

        prepared = {key: value for key, value in data.items() if key in allowed}
        for key in ["origin_lat", "origin_lng", "destination_lat", "destination_lng"]:
            if key in prepared:
                prepared[key] = self._finite_float(prepared[key])

        if "travel_mode" in prepared:
            mode = prepared["travel_mode"] or "auto"
            if mode not in TRIP_TRAVEL_MODES:
                raise ValueError("Unsupported travel mode")
            prepared["travel_mode"] = mode
            if "transport_mode_priority" not in prepared:
                prepared["transport_mode_priority"] = json.dumps(
                    normalize_priority(None, mode)
                )
        if "route_order_mode" in prepared:
            prepared["route_order_mode"] = validate_route_order_mode(
                prepared["route_order_mode"]
            )
        if "transport_mode_priority" in prepared:
            priority = normalize_priority(
                prepared["transport_mode_priority"], prepared.get("travel_mode")
            )
            prepared["transport_mode_priority"] = json.dumps(priority)
        validate_time_windows(prepared)
        if "avoid_weekends" in prepared:
            prepared["avoid_weekends"] = 1 if prepared["avoid_weekends"] else 0
        if "holiday_dates" in prepared:
            prepared["holiday_dates"] = json.dumps(self._clean_holiday_dates(prepared["holiday_dates"]))
        if "itinerary_summary" in prepared:
            prepared["itinerary_summary"] = json.dumps(prepared["itinerary_summary"], ensure_ascii=False)
        return prepared

    def _clean_holiday_dates(self, value) -> list[str]:
        return self._parse_holiday_dates(value)[0]

    def _parse_holiday_dates(self, value) -> tuple[list[str], list[str]]:
        return parse_holiday_dates(value)

    def _clean_stay_days(self, value) -> int:
        return clean_stay_days(value)

    def _clean_stop_stays(self, value) -> dict[str, int]:
        if not isinstance(value, dict):
            return {}
        result = {}
        for stop_id, days in value.items():
            result[str(stop_id)] = self._clean_stay_days(days)
        return result

    def _clean_half_days(self, value, field: str = "half_days") -> int:
        if isinstance(value, bool):
            raise ValueError("Visit duration must be 0.5 to 30 days in half-day steps")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Visit duration must be 0.5 to 30 days in half-day steps"
            ) from exc
        if result < 1 or result > 60:
            raise ValueError("Visit duration must be 0.5 to 30 days in half-day steps")
        return result

    def _clean_stop_durations(
        self, data: dict, active_ids: set[str]
    ) -> dict[str, dict]:
        if "stop_durations" in data and "stop_stays" in data:
            raise ValueError(
                "Choose either half-day visit durations or legacy full-day stays, not both"
            )
        if "stop_stays" in data:
            legacy = self._clean_stop_stays(data.get("stop_stays") or {})
            unknown = set(legacy) - active_ids
            if unknown:
                raise ValueError("Unknown stop duration: " + ", ".join(sorted(unknown)))
            return {
                stop_id: {"half_days": days * 2}
                for stop_id, days in legacy.items()
            }
        raw = data.get("stop_durations")
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError("stop_durations must be keyed by stop ID")
        unknown = set(str(value) for value in raw) - active_ids
        if unknown:
            raise ValueError("Unknown stop duration: " + ", ".join(sorted(unknown)))
        result = {}
        for raw_stop_id, value in raw.items():
            stop_id = str(raw_stop_id)
            if not isinstance(value, dict):
                raise ValueError(f"stop_durations[{stop_id}] must be an object")
            unknown_fields = set(value) - {"half_days", "preferred_period", "locked"}
            if unknown_fields:
                raise ValueError(f"Unknown fields in stop_durations[{stop_id}]")
            item = {}
            if "half_days" in value:
                item["half_days"] = self._clean_half_days(
                    value["half_days"], f"stop_durations[{stop_id}].half_days"
                )
            if "preferred_period" in value:
                period = value["preferred_period"] or "auto"
                if period not in {"auto", "AM", "PM"}:
                    raise ValueError(
                        f"stop_durations[{stop_id}].preferred_period must be auto, AM or PM"
                    )
                item["preferred_period"] = period
            if "locked" in value:
                item["locked"] = bool(value["locked"])
            result[stop_id] = item
        return result

    def _next_work_slot(
        self,
        slot: tuple[date, str],
        avoid_weekends: bool,
        holidays: list[str],
    ) -> tuple[date, str]:
        day, period = slot
        if self._is_workday(day, avoid_weekends, holidays):
            return day, period
        return self._next_workday(day, avoid_weekends, holidays), "AM"

    def _window_slot(
        self, value, *, default_period: str
    ) -> Optional[tuple[date, str]]:
        if not value:
            return None
        text = str(value).strip()
        day = self._parse_date(text)
        if not day:
            raise ValueError("Trip time window must be a valid ISO date/time")
        has_explicit_time = "T" in text or (
            " " in text and ":" in text.split(" ", 1)[1]
        )
        if not has_explicit_time:
            return day, default_period
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Trip time window must be a valid ISO date/time") from exc
        return day, "AM" if parsed.hour < 12 else "PM"

    def _after_work_slot(
        self,
        slot: tuple[date, str],
        avoid_weekends: bool,
        holidays: list[str],
    ) -> tuple[date, str]:
        day, period = slot
        if period == "AM":
            return self._next_work_slot((day, "PM"), avoid_weekends, holidays)
        return self._next_work_slot(
            (day + timedelta(days=1), "AM"), avoid_weekends, holidays
        )

    def _after_calendar_slot(self, slot: tuple[date, str]) -> tuple[date, str]:
        day, period = slot
        if period == "AM":
            return day, "PM"
        return day + timedelta(days=1), "AM"

    def _allocate_calendar_slots(
        self,
        start_slot: tuple[date, str],
        count: int,
    ) -> tuple[list[tuple[date, str]], tuple[date, str]]:
        """Occupy consecutive half-days including weekends and holidays."""
        cursor = start_slot
        slots = []
        for _ in range(max(0, int(count))):
            slots.append(cursor)
            cursor = self._after_calendar_slot(cursor)
        return slots, cursor

    def _allocate_work_slots(
        self,
        start_slot: tuple[date, str],
        count: int,
        avoid_weekends: bool,
        holidays: list[str],
    ) -> tuple[list[tuple[date, str]], tuple[date, str]]:
        cursor = self._next_work_slot(start_slot, avoid_weekends, holidays)
        slots = []
        for _ in range(max(0, int(count))):
            slots.append(cursor)
            cursor = self._after_work_slot(cursor, avoid_weekends, holidays)
        return slots, cursor

    @staticmethod
    def _slot_key(slot: tuple[date, str]) -> tuple[str, int]:
        return slot[0].isoformat(), 0 if slot[1] == "AM" else 1

    def _seek_preferred_period(
        self,
        cursor: tuple[date, str],
        preferred: str,
        avoid_weekends: bool,
        holidays: list[str],
        calendar_only: bool = False,
    ) -> tuple[date, str]:
        if preferred == "auto" or cursor[1] == preferred:
            return cursor
        if preferred == "PM" and cursor[1] == "AM":
            return cursor[0], "PM"
        if calendar_only:
            return self._after_calendar_slot(cursor)
        return self._after_work_slot(cursor, avoid_weekends, holidays)

    def _calendar_slots_after(
        self,
        boundary: tuple[date, str],
        actual: tuple[date, str],
    ) -> int:
        """Half-days by which ``actual`` passes ``boundary`` on the calendar.

        The requested end date is a calendar deadline: a return that lands on a
        Saturday is late even though Saturday is not a working day.
        """
        if self._slot_key(actual) <= self._slot_key(boundary):
            return 0
        count = 0
        cursor = self._after_calendar_slot(boundary)
        while self._slot_key(cursor) <= self._slot_key(actual):
            count += 1
            cursor = self._after_calendar_slot(cursor)
        return count

    def _work_slots_after(
        self,
        boundary: tuple[date, str],
        actual: tuple[date, str],
        avoid_weekends: bool,
        holidays: list[str],
    ) -> int:
        if self._slot_key(actual) <= self._slot_key(boundary):
            return 0
        count = 0
        cursor = self._after_work_slot(boundary, avoid_weekends, holidays)
        while self._slot_key(cursor) <= self._slot_key(actual):
            count += 1
            cursor = self._after_work_slot(cursor, avoid_weekends, holidays)
        return count

    def _route_endpoint(self, prefix: str, data: dict, plan: dict) -> Optional[dict]:
        lat = data.get(f"{prefix}_lat", plan.get(f"{prefix}_lat"))
        lng = data.get(f"{prefix}_lng", plan.get(f"{prefix}_lng"))
        lat = self._finite_float(lat)
        lng = self._finite_float(lng)
        if lat is None or lng is None:
            return None
        label = data.get(f"{prefix}_name") or plan.get(f"{prefix}_name") or prefix.title()
        return {"label": label, "lat": lat, "lng": lng}

    def _route_point_from_stop(self, stop: dict) -> Optional[dict]:
        visit_location = stop.get("visit_location") or {}
        lat = self._finite_float(visit_location.get("lat", stop.get("lat")))
        lng = self._finite_float(visit_location.get("lng", stop.get("lng")))
        if lat is None or lng is None:
            return None
        label = (
            visit_location.get("label")
            or visit_location.get("name")
            or
            stop.get("location_name")
            or stop.get("customer_name")
            or stop.get("customer_id")
            or "Stop"
        )
        location = ", ".join(
            x for x in [
                visit_location.get("city", stop.get("city")),
                visit_location.get("country", stop.get("country")),
            ] if x
        )
        if location:
            label = f"{label} ({location})"
        return {"label": label, "lat": lat, "lng": lng}

    def _order_route_stops(
        self,
        origin: dict,
        destination: Optional[dict],
        stops: list[tuple[dict, dict]],
        priority: list[str],
    ) -> list[tuple[dict, dict]]:
        # Airports and transit points belong to the visit they serve, so they are
        # ordered as one chain instead of being scattered across the route.
        remaining = anchor_waypoints(stops)
        ordered = []
        current = origin
        while remaining:
            next_chain = min(
                remaining,
                key=lambda chain: (
                    self._route_distance_score(current, chain[-1][1], priority)
                    + (
                        self._route_distance_score(chain[-1][1], destination, priority) * 0.15
                        if destination else 0
                    )
                ),
            )
            ordered.extend(next_chain)
            remaining.remove(next_chain)
            current = next_chain[-1][1]
        return ordered

    def _route_distance_score(
        self,
        start: Optional[dict],
        end: Optional[dict],
        priority: list[str],
    ) -> float:
        if not start or not end:
            return 0
        distance_km = self._haversine_km(start["lat"], start["lng"], end["lat"], end["lng"])
        selected_mode = select_mode(distance_km, priority)
        estimate_mode = selected_mode if selected_mode != "other" else "drive"
        return self._estimate_travel_leg(start, end, estimate_mode)["time_hours"]

    def _shared_leg_settings(self, plan_id: str) -> dict:
        """Stored leg settings for the single-path calculation.

        The repository keys everything by ``(member_id, leg_key)`` so two
        colleagues covering the same pair of stops keep separate airports and
        transport. This calculation is the shared path, whose legs belong to no
        member, so it reads that slice and keeps its own plain leg keys.
        """
        repo = self.trip_plan_service.leg_repo
        stored: dict = {}
        for (member_id, leg_key), value in repo.locked_overrides(plan_id).items():
            if member_id is None:
                stored[leg_key] = dict(value)
        for (member_id, leg_key), airports in repo.saved_airports(plan_id).items():
            if member_id is None:
                stored.setdefault(leg_key, {}).update(airports)
        return stored

    def _expand_flight_leg(
        self, leg: dict, start_point: dict, end_point: dict, priority: list[str]
    ) -> Optional[list[dict]]:
        """Describe a flown connection as its ground transfers and the flight.

        Returns ``None`` when the leg is not a fully described flight, so the
        caller keeps treating it as a single segment.
        """
        if not is_expandable(leg):
            return None
        departure = airport_point(leg, "departure")
        arrival = airport_point(leg, "arrival")
        transfer = ground_mode(priority)
        hops = (
            ("to_airport", transfer, start_point, departure),
            ("flight", "flight", departure, arrival),
            ("from_airport", transfer, arrival, end_point),
        )
        segments = []
        for role, mode, left, right in hops:
            estimate = self._estimate_travel_leg(left, right, mode)
            hours = float(estimate["time_hours"])
            segments.append(
                {
                    "role": role,
                    "selected_mode": mode,
                    "from_label": left.get("label"),
                    "to_label": right.get("label"),
                    "distance_km": round(float(estimate["distance_km"]), 1),
                    "time_hours": round(hours, 1),
                    "travel_half_days": travel_calendar_half_days(hours),
                    "stay_half_days": int(
                        (right or {}).get("stay_half_days") or 0
                    ) if role != "from_airport" else 0,
                    "stay_label": (right or {}).get("label") if role != "from_airport" else None,
                }
            )
        return segments

    def _estimate_travel_leg(self, start: dict, end: dict, requested_mode: str) -> dict:
        km = self._haversine_km(start["lat"], start["lng"], end["lat"], end["lng"])
        mode = requested_mode
        if requested_mode == "auto":
            if km >= 700:
                mode = "flight"
            elif km >= 250:
                mode = "ground_public"
            else:
                mode = "drive"

        if km <= 5:
            distance_km = km
            hours = 0.25
            travel_days = 0
        elif mode == "flight":
            distance_km = km
            hours = 3.0 + km / 780
            if km > 6000:
                hours += 2.0
            travel_days = 1 if hours <= 10 else 2
        elif mode == "ground_public":
            distance_km = km * 1.15
            hours = 1.25 + distance_km / 95
            travel_days = 0 if hours <= 4 else max(1, math.ceil(hours / 7))
        else:
            distance_km = km * 1.18
            hours = 0.5 + distance_km / 75
            travel_days = 0 if hours <= 3.5 else max(1, math.ceil(hours / 7))

        return {
            "from": start.get("label"),
            "to": end.get("label"),
            "mode": mode,
            "distance_km": round(distance_km, 1),
            "time_hours": round(hours, 1),
            "travel_days": int(travel_days),
        }

    def _haversine_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        radius_km = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lam = math.radians(lng2 - lng1)
        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lam / 2) ** 2
        )
        return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _next_workday(self, day: date, avoid_weekends: bool, holidays: list[str]) -> date:
        cursor = day
        while not self._is_workday(cursor, avoid_weekends, holidays):
            cursor += timedelta(days=1)
        return cursor

    def _add_workdays_inclusive(
        self,
        start: date,
        count: int,
        avoid_weekends: bool,
        holidays: list[str],
    ) -> date:
        cursor = self._next_workday(start, avoid_weekends, holidays)
        remaining = max(1, int(count)) - 1
        while remaining > 0:
            cursor += timedelta(days=1)
            if self._is_workday(cursor, avoid_weekends, holidays):
                remaining -= 1
        return cursor

    def _business_days_between(
        self,
        start: date,
        end: date,
        avoid_weekends: bool,
        holidays: list[str],
    ) -> int:
        if end < start:
            return 0
        total = 0
        cursor = start
        while cursor <= end:
            if self._is_workday(cursor, avoid_weekends, holidays):
                total += 1
            cursor += timedelta(days=1)
        return total

    def _is_workday(self, day: date, avoid_weekends: bool, holidays: list[str]) -> bool:
        if day.isoformat() in holidays:
            return False
        if avoid_weekends and day.weekday() >= 5:
            return False
        return True

    def _finite_float(self, value) -> Optional[float]:
        return finite_float(value)

    def _assert_row_version(self, row: dict, expected_version: Optional[int]) -> None:
        if expected_version is None:
            return
        current_version = int(row.get("row_version") or 1)
        if current_version != int(expected_version):
            raise ConflictError(
                current_version=current_version,
                your_version=int(expected_version),
                current_data={
                    "id": row.get("id"),
                    "updated_at": row.get("updated_at"),
                },
            )

    def _get_trip_stop(self, stop_id: str) -> Optional[dict]:
        row = self.lead_repo.conn.execute(
            "SELECT * FROM trip_plan_stops WHERE id = ? AND archived_at IS NULL",
            (stop_id,),
        ).fetchone()
        return dict(row) if row else None

    def _normalize_trip_stop_sequences(self, plan_id: str, actor_id: str, timestamp: str) -> None:
        self.trip_plan_service.free_stop_repo.normalize_sequences(
            plan_id, actor_id, timestamp
        )

    def _can_access_plan(self, plan: dict, actor_id: str, actor_role: str) -> bool:
        return self.visibility_service.can_access_plan(plan, actor_id, actor_role)

    def _sync_trip_result_activity(self, stop: dict, actor_id: str) -> None:
        if not stop.get("lead_id"):
            return
        status = stop.get("result_status") or "Planned"
        if status == "Planned" and not stop.get("result_notes"):
            return

        summary = f"Trip visit: {status}"
        if stop.get("result_notes"):
            summary = f"{summary} - {stop['result_notes'][:160]}"
        payload = json.dumps(
            {
                "trip_plan_id": stop.get("plan_id"),
                "trip_stop_id": stop.get("id"),
                "result_status": status,
                "result_notes": stop.get("result_notes"),
                "visit_purpose": stop.get("visit_purpose"),
                "customer_needs": stop.get("visit_customer_needs"),
                "competitor": stop.get("visit_competitor"),
                "budget": stop.get("visit_budget"),
                "decision_maker": stop.get("visit_decision_maker"),
                "next_action": stop.get("visit_next_action"),
                "sample_needed": bool(stop.get("visit_sample_needed")),
                "quote_needed": bool(stop.get("visit_quote_needed")),
            }
        )
        if stop.get("result_activity_id"):
            self.lead_repo.conn.execute(
                """
                UPDATE lead_activities
                SET summary = ?, payload_json = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (summary[:200], payload, stop["result_activity_id"]),
            )
            return

        activity_id = generate_uuid()
        self.lead_repo.conn.execute(
            """
            INSERT INTO lead_activities (
                id, lead_id, actor_id, action_type, visibility,
                is_formal_follow_up, summary, payload_json,
                changed_field, before_value, after_value, created_at
            ) VALUES (?, ?, ?, 'comment', 'all', 0, ?, ?, NULL, NULL, NULL, ?)
            """,
            (activity_id, stop["lead_id"], actor_id, summary[:200], payload, now_iso()),
        )
        self.lead_repo.conn.execute(
            """
            UPDATE trip_plan_stops
            SET result_activity_id = ?, updated_at = ?, updated_by = ?,
                row_version = row_version + 1
            WHERE id = ?
            """,
            (activity_id, now_iso(), actor_id, stop["id"]),
        )

    def _sync_trip_lead_next_followup_date(self, lead_id: str, actor_id: str) -> None:
        """Derive the Lead due date from every active formal follow-up."""
        conn = self.lead_repo.conn
        rows = conn.execute(
            """
            SELECT payload_json
            FROM lead_activities
            WHERE lead_id = ? AND action_type = 'follow_up'
              AND is_formal_follow_up = 1 AND archived_at IS NULL
            """,
            (lead_id,),
        ).fetchall()
        dates = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                payload = {}
            value = payload.get("next_action_date")
            if isinstance(value, str) and value.strip():
                dates.append(value.strip())
        next_due = min(dates) if dates else None
        lead = conn.execute(
            "SELECT next_followup_date FROM leads WHERE id = ? AND archived_at IS NULL",
            (lead_id,),
        ).fetchone()
        if lead and lead["next_followup_date"] != next_due:
            conn.execute(
                """
                UPDATE leads
                SET next_followup_date = ?, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE id = ? AND archived_at IS NULL
                """,
                (next_due, now_iso(), actor_id, lead_id),
            )

    def _sync_trip_followup_activity(
        self,
        stop: dict,
        actor_id: str,
        previous_lead_id: Optional[str] = None,
    ) -> None:
        """Create, update or archive the formal follow-up owned by a Trip stop."""
        conn = self.lead_repo.conn
        lead_id = stop.get("lead_id")
        affected_leads = {value for value in (previous_lead_id, lead_id) if value}
        activity_id = stop.get("followup_activity_id")
        activity = None
        if activity_id:
            row = conn.execute(
                "SELECT * FROM lead_activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
            activity = dict(row) if row else None
            if activity and activity.get("lead_id"):
                affected_leads.add(activity["lead_id"])

        next_action = str(stop.get("visit_next_action") or "").strip()
        should_have_followup = bool(
            lead_id
            and stop.get("result_status") == "Follow-up Needed"
            and next_action
        )
        linked_is_active = bool(
            activity
            and activity.get("archived_at") is None
            and activity.get("action_type") == "follow_up"
            and bool(activity.get("is_formal_follow_up"))
            and activity.get("lead_id") == lead_id
        )

        if activity_id and (not should_have_followup or not linked_is_active):
            if (
                activity
                and activity.get("archived_at") is None
                and activity.get("action_type") == "follow_up"
                and bool(activity.get("is_formal_follow_up"))
            ):
                conn.execute(
                    "UPDATE lead_activities SET archived_at = ? WHERE id = ? AND archived_at IS NULL",
                    (now_iso(), activity_id),
                )
            conn.execute(
                """
                UPDATE trip_plan_stops
                SET followup_activity_id = NULL, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE id = ? AND followup_activity_id = ?
                """,
                (now_iso(), actor_id, stop["id"], activity_id),
            )
            activity_id = None
            linked_is_active = False

        if should_have_followup:
            due_date = str(stop.get("visit_followup_due_date") or "").strip() or None
            payload_data = {
                "method": "Trip Visit",
                "content": next_action,
                "status": "pending",
                "next_action": next_action,
                "source": "trip_visit_execution",
                "trip_plan_id": stop.get("plan_id"),
                "trip_stop_id": stop.get("id"),
            }
            if due_date:
                payload_data["next_action_date"] = due_date
            payload = json.dumps(payload_data, ensure_ascii=False)
            summary = f"Trip follow-up: {next_action}"[:200]

            if linked_is_active and activity_id:
                conn.execute(
                    """
                    UPDATE lead_activities
                    SET summary = ?, payload_json = ?
                    WHERE id = ? AND archived_at IS NULL
                    """,
                    (summary, payload, activity_id),
                )
            else:
                activity_id = generate_uuid()
                conn.execute(
                    """
                    INSERT INTO lead_activities (
                        id, lead_id, actor_id, action_type, visibility,
                        is_formal_follow_up, summary, payload_json,
                        changed_field, before_value, after_value, created_at
                    ) VALUES (?, ?, ?, 'follow_up', 'all', 1, ?, ?, NULL, NULL, NULL, ?)
                    """,
                    (activity_id, lead_id, actor_id, summary, payload, now_iso()),
                )
                conn.execute(
                    """
                    UPDATE trip_plan_stops
                    SET followup_activity_id = ?, updated_at = ?, updated_by = ?,
                        row_version = row_version + 1
                    WHERE id = ?
                    """,
                    (activity_id, now_iso(), actor_id, stop["id"]),
                )

            conn.execute(
                """
                UPDATE leads
                SET sales_stage = 'Following', updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE id = ? AND archived_at IS NULL
                  AND sales_stage IN ('New', 'Assigned')
                """,
                (now_iso(), actor_id, lead_id),
            )

        for affected_lead_id in affected_leads:
            self._sync_trip_lead_next_followup_date(affected_lead_id, actor_id)

    def _num(self, value) -> float:
        return num(value)

    def _days_since(self, value: Optional[str], today: date) -> Optional[int]:
        parsed = self._parse_date(value)
        if not parsed:
            return None
        return (today - parsed).days

    def _parse_date(self, value: Optional[str]) -> Optional[date]:
        return parse_date(value)

    def _md_cell(self, value) -> str:
        return md_cell(value)

    def _csv_cell(self, value):
        return csv_cell(value)

    def _load_country_lookup(self) -> dict:
        """Load country centers and region mapping from local config."""
        lookup = {"countries": {}, "name_to_code": {}, "aliases": {"UK": "GB", "UAE": "AE", "USA": "US"}}
        config_path = Path(__file__).parents[2] / "config" / "regions.json"
        if not config_path.exists():
            return lookup

        data = json.loads(config_path.read_text(encoding="utf-8"))
        for region_code, region in data.get("regions", {}).items():
            for code, country in region.get("countries", {}).items():
                item = {**country, "region": region_code, "code": code}
                lookup["countries"][code] = item
                lookup["name_to_code"][country.get("name", "").lower()] = code
                lookup["name_to_code"][country.get("name_cn", "").lower()] = code
        return lookup

    def _normalize_country(self, value: Optional[str]) -> Optional[str]:
        """Normalize country code/name to a configured ISO-like code."""
        return self.country_service.country_code(value)

    def _country_center(self, country_code: Optional[str]) -> Optional[dict]:
        return self.country_service.center(country_code)

    def _country_region(self, country_code: Optional[str]) -> Optional[str]:
        return self.country_service.region(country_code)

    def _country_name(self, country_code: Optional[str]) -> Optional[str]:
        return self.country_service.display_name(country_code)

    def _map_missing_location(self, group: dict) -> dict:
        """Return a compact customer row for coordinate cleanup queues."""
        return {
            "customer_id": group["customer_id"],
            "customer_name": group["customer_name"],
            "country": group.get("country"),
            "city": group.get("city"),
            "postal_code": group.get("postal_code"),
            "address": group.get("address"),
            "customer_row_version": group.get("customer_row_version"),
            "can_edit": bool(group.get("can_edit")),
            "invalid_coordinates": bool(group.get("invalid_coordinates")),
            "lead_count": len(group["leads"]),
            "latest_lead_id": group["leads"][0]["id"] if group["leads"] else None,
        }
