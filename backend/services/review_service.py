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
from .trip_working_import import TripWorkingImportService
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


def _answer_value(value):
    """The stored answer as JSON sees it: unanswered, yes or no."""
    return None if value is None else bool(value)


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
        self.trip_working_import_service = TripWorkingImportService(self)

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

    def suggest_trip_flexible_visits(
        self, plan_id: str, data: dict, actor_id: str, actor_role: str
    ) -> Optional[dict]:
        return self.trip_plan_service.suggest_trip_flexible_visits(
            plan_id, data, actor_id, actor_role
        )

    def set_trip_member(
        self, plan_id: str, data: dict, actor_id: str, actor_role: str
    ) -> Optional[dict]:
        return self.trip_plan_service.set_trip_member(
            plan_id, data, actor_id, actor_role
        )

    def remove_trip_member(
        self, plan_id: str, user_id: str, actor_id: str, actor_role: str
    ) -> Optional[dict]:
        return self.trip_plan_service.remove_trip_member(
            plan_id, user_id, actor_id, actor_role
        )

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

    def export_trip_plan_xlsx(self, plan_id: str, actor_id: str, actor_role: str,
                              variant: str = "full") -> Optional[bytes]:
        return self.trip_plan_service.export_trip_plan_xlsx(
            plan_id, actor_id, actor_role, variant
        )

    def export_trip_plan_html(self, plan_id: str, actor_id: str, actor_role: str,
                              variant: str = "full") -> Optional[bytes]:
        return self.trip_plan_service.export_trip_plan_html(
            plan_id, actor_id, actor_role, variant
        )

    def export_trip_plan_ics(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[bytes]:
        return self.trip_plan_service.export_trip_plan_ics(plan_id, actor_id, actor_role)

    def export_trip_working_xlsx(
        self, plan_id: str, actor_id: str, actor_role: str
    ) -> Optional[bytes]:
        return self.trip_plan_service.export_trip_working_xlsx(
            plan_id, actor_id, actor_role
        )

    def preflight_trip_working(self, content: bytes, filename: str, actor_id: str, actor_role: str) -> dict:
        return self.trip_working_import_service.preflight(
            content, filename, actor_id, actor_role
        )

    def import_trip_working(
        self, content: bytes, filename: str, expected_source_hash: str,
        expected_preview_digest: str, resolutions: dict,
        actor_id: str, actor_role: str,
    ) -> dict:
        return self.trip_working_import_service.commit(
            content, filename, expected_source_hash, expected_preview_digest,
            resolutions, actor_id, actor_role,
        )

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
                # The separate travel windows no longer bound a route: the
                # plan's own dates do. Old plans still carry what was typed
                # into them, and a preview reports the plan as it stands.
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
            "planning_mode",
        }
        if include_system_fields:
            allowed.update({"itinerary_generated_at", "itinerary_summary"})

        prepared = {key: value for key, value in data.items() if key in allowed}
        for key in ["origin_lat", "origin_lng", "destination_lat", "destination_lng"]:
            if key in prepared:
                prepared[key] = self._finite_float(prepared[key])

        if "planning_mode" in prepared:
            text = str(prepared["planning_mode"] or "").strip().lower()
            prepared["planning_mode"] = text if text in ("legacy", "team") else "legacy"

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

    def _after_slots(self, slot: tuple, count: int) -> tuple:
        """The half-day reached after occupying ``count`` calendar half-days."""
        cursor = slot
        for _ in range(max(0, int(count))):
            cursor = self._after_calendar_slot(cursor)
        return cursor

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

    def _team_leg_settings(self, plan_id: str, team: tuple,
                           incoming: dict | None = None) -> dict:
        """Leg settings keyed by member, for the team calculation.

        What is stored comes back keyed by who travelled it. What the browser
        sends is keyed by the connection alone, because the route shows one row
        for a journey colleagues make together and one choice is made on it, so
        it applies to everybody on that connection. Without this the mode a user
        picks is dropped on the way in and the next draw shows it unset again.
        """
        repo = self.trip_plan_service.leg_repo
        stored: dict = {}
        for key, value in repo.locked_overrides(plan_id).items():
            if key[0] in team:
                stored[key] = dict(value)
        for key, airports in repo.saved_airports(plan_id).items():
            if key[0] in team:
                stored.setdefault(key, {}).update(airports)
        for leg_key, value in (incoming or {}).items():
            for user in team:
                stored.setdefault((user, leg_key), {}).update(dict(value))
        return stored

    def _team_plan_settings(self, plan: dict, data: dict) -> dict:
        """When the trip starts, how people travel, and when it has to be over.

        A team trip is bounded by the plan's own dates. The separate departure
        and return windows said the same thing a second time, in a second place,
        for the whole team at once - and a member who leaves on their own day
        already says so on their own row. One window, on the plan, is the thing
        every member's dates are checked against.
        """
        start = self._parse_date(
            data.get("start_date") or plan.get("start_date")
        )
        if not start:
            raise ValueError(
                "start_date is required before generating an itinerary"
            )
        end_value = (
            data.get("end_date") if "end_date" in data else plan.get("end_date")
        )
        travel_mode = data.get("travel_mode") or plan.get("travel_mode") or "auto"
        if travel_mode not in TRIP_TRAVEL_MODES:
            raise ValueError("Unsupported travel mode")
        if "transport_mode_priority" in data:
            priority = normalize_priority(
                data.get("transport_mode_priority"), travel_mode
            )
        elif "travel_mode" in data:
            priority = normalize_priority(None, travel_mode)
        else:
            priority = normalize_priority(
                plan.get("transport_mode_priority"), travel_mode
            )
        end = self._parse_date(end_value)
        holidays, _ = self._parse_holiday_dates(
            data.get("holiday_dates") if "holiday_dates" in data
            else plan.get("holiday_dates")
        )
        avoid_weekends = (
            data.get("avoid_weekends") if "avoid_weekends" in data
            else plan.get("avoid_weekends", True)
        )
        return {
            "initial_slot": (start, "AM"),
            "priority": priority,
            "end": end,
            "return_end": end,
            "avoid_weekends": bool(avoid_weekends),
            "holidays": tuple(holidays),
        }

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
        # What the reader typed on the connection describes the flight: those
        # are the hours and the days of the flight they looked up. The drives at
        # either end each have their own field. Anything not given is estimated.
        hops = (
            ("to_airport",
             leg.get("departure_transfer_mode") or transfer,
             start_point, departure,
             leg.get("departure_transfer_half_days"),
             leg.get("departure_transfer_time_hours"), None),
            ("flight", "flight", departure, arrival,
             leg.get("manual_travel_half_days"),
             leg.get("manual_time_hours"), leg.get("manual_distance_km")),
            ("from_airport",
             leg.get("arrival_transfer_mode") or transfer,
             arrival, end_point,
             leg.get("arrival_transfer_half_days"),
             leg.get("arrival_transfer_time_hours"), None),
        )
        segments = []
        for role, mode, left, right, half_days, given_hours, given_km in hops:
            estimate = self._estimate_travel_leg(left, right, mode)
            hours = float(
                given_hours if given_hours is not None
                else estimate["time_hours"]
            )
            distance = float(
                given_km if given_km is not None else estimate["distance_km"]
            )
            segments.append(
                {
                    "role": role,
                    "selected_mode": mode,
                    "from_label": left.get("label"),
                    "to_label": right.get("label"),
                    "distance_km": round(distance, 1),
                    "time_hours": round(hours, 1),
                    "travel_half_days": (
                        min(60, int(half_days)) if half_days is not None
                        else travel_calendar_half_days(hours)
                    ),
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
                # None stays None: the activity must not record an answer
                # nobody gave.
                "sample_needed": _answer_value(stop.get("visit_sample_needed")),
                "quote_needed": _answer_value(stop.get("visit_quote_needed")),
                "actual_visit_date": stop.get("actual_visit_date"),
                "actual_visit_period": stop.get("actual_visit_period"),
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
