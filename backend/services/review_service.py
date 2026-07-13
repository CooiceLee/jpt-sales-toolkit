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

from ..repositories import LeadRepository, CustomerRepository, ActivityRepository
from ..repositories.base import ConflictError, generate_uuid, now_iso
from .country_service import CountryService
from .review_analysis_service import ReviewAnalysisService
from .review_map_service import ReviewMapService
from .review_utils import clean_stay_days, csv_cell, finite_float, md_cell, num, parse_date, parse_holiday_dates
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

TRIP_TRAVEL_MODES = {"auto", "drive", "ground_public", "flight"}


class ReviewService:
    """Review and analytics service."""

    def __init__(
        self,
        lead_repo: Optional[LeadRepository] = None,
        customer_repo: Optional[CustomerRepository] = None,
        activity_repo: Optional[ActivityRepository] = None,
    ):
        self.lead_repo = lead_repo or LeadRepository()
        self.customer_repo = customer_repo or CustomerRepository()
        self.activity_repo = activity_repo or ActivityRepository()
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

    def archive_trip_stop(
        self,
        plan_id: str,
        stop_id: str,
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> Optional[dict]:
        return self.trip_plan_service.archive_trip_stop(plan_id, stop_id, actor_id, actor_role, row_version)

    def export_trip_plan_markdown(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[str]:
        return self.trip_plan_service.export_trip_plan_markdown(plan_id, actor_id, actor_role)

    def export_trip_plan_csv(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[str]:
        return self.trip_plan_service.export_trip_plan_csv(plan_id, actor_id, actor_role)

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

    def _calculate_trip_itinerary(self, plan: dict, data: dict) -> dict:
        stops = plan.get("stops") or []
        if not stops:
            raise ValueError("Add at least one stop before generating an itinerary")

        start = self._parse_date(data.get("start_date") or plan.get("start_date"))
        if not start:
            raise ValueError("start_date is required before generating an itinerary")

        travel_mode = data.get("travel_mode") or plan.get("travel_mode") or "auto"
        if travel_mode not in TRIP_TRAVEL_MODES:
            raise ValueError("Unsupported travel mode")
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
                missing_locations.append(stop.get("customer_name") or stop.get("customer_id"))
                continue
            routable_stops.append((stop, point))
        if missing_locations:
            raise ValueError("Stops need latitude and longitude: " + ", ".join(missing_locations[:5]))

        stop_stays = self._clean_stop_stays(data.get("stop_stays") or {})
        origin = self._route_endpoint("origin", data, plan) or routable_stops[0][1]
        destination = self._route_endpoint("destination", data, plan) or routable_stops[-1][1]
        ordered_stops = self._order_route_stops(origin, destination, routable_stops, travel_mode)

        current_point = origin
        cursor = start
        total_distance = 0.0
        total_hours = 0.0
        total_travel_days = 0
        stop_updates = []
        last_visit_end = start

        for sequence_no, (stop, point) in enumerate(ordered_stops, start=1):
            leg = self._estimate_travel_leg(current_point, point, travel_mode)
            travel_days = int(leg["travel_days"])
            if travel_days > 0:
                travel_end = self._add_workdays_inclusive(cursor, travel_days, avoid_weekends, holidays)
                visit_start = self._next_workday(travel_end + timedelta(days=1), avoid_weekends, holidays)
            else:
                visit_start = self._next_workday(cursor, avoid_weekends, holidays)

            stay_days = stop_stays.get(stop["id"], self._clean_stay_days(stop.get("stay_days")))
            visit_end = self._add_workdays_inclusive(visit_start, stay_days, avoid_weekends, holidays)
            stop_updates.append(
                {
                    "id": stop["id"],
                    "sequence_no": sequence_no,
                    "planned_date": visit_start.isoformat(),
                    "planned_end_date": visit_end.isoformat(),
                    "stay_days": stay_days,
                    "travel_from_label": current_point.get("label"),
                    "travel_mode": leg["mode"],
                    "travel_distance_km": leg["distance_km"],
                    "travel_time_hours": leg["time_hours"],
                    "travel_days": travel_days,
                }
            )

            total_distance += leg["distance_km"]
            total_hours += leg["time_hours"]
            total_travel_days += travel_days
            current_point = point
            cursor = visit_end + timedelta(days=1)
            last_visit_end = visit_end

        final_leg = self._estimate_travel_leg(current_point, destination, travel_mode) if destination else None
        calculated_end = last_visit_end
        if final_leg:
            final_days = int(final_leg["travel_days"])
            total_distance += final_leg["distance_km"]
            total_hours += final_leg["time_hours"]
            total_travel_days += final_days
            if final_days > 0:
                calculated_end = self._add_workdays_inclusive(
                    last_visit_end + timedelta(days=1),
                    final_days,
                    avoid_weekends,
                    holidays,
                )

        summary = {
            "generated_at": now_iso(),
            "start_date": start.isoformat(),
            "calculated_end_date": calculated_end.isoformat(),
            "stop_count": len(ordered_stops),
            "total_stay_days": sum(item["stay_days"] for item in stop_updates),
            "total_travel_days": total_travel_days,
            "total_business_days": self._business_days_between(start, calculated_end, avoid_weekends, holidays),
            "total_calendar_days": (calculated_end - start).days + 1,
            "total_distance_km": round(total_distance, 1),
            "total_travel_hours": round(total_hours, 1),
            "travel_mode": travel_mode,
            "avoid_weekends": bool(avoid_weekends),
            "holiday_dates": holidays,
            "warnings": warnings,
            "final_leg": final_leg,
        }
        plan_updates = self._prepare_trip_plan_data(
            {
                **data,
                "start_date": start.isoformat(),
                "end_date": calculated_end.isoformat(),
                "travel_mode": travel_mode,
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
            "plan_updates": plan_updates,
        }

    def _trip_itinerary_preview_plan(self, plan: dict, calculation: dict) -> dict:
        preview = {**plan}
        summary = calculation["summary"]
        preview.update(
            {
                "start_date": summary["start_date"],
                "end_date": summary["calculated_end_date"],
                "travel_mode": summary["travel_mode"],
                "avoid_weekends": summary["avoid_weekends"],
                "holiday_dates": summary["holiday_dates"],
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
        return preview

    def _normalize_trip_plan_row(self, row: dict) -> dict:
        row["avoid_weekends"] = bool(row.get("avoid_weekends", 1))
        row["holiday_dates"] = self._clean_holiday_dates(row.get("holiday_dates"))
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
        lat = self._finite_float(stop.get("lat"))
        lng = self._finite_float(stop.get("lng"))
        if lat is None or lng is None:
            return None
        label = stop.get("customer_name") or stop.get("customer_id") or "Stop"
        location = ", ".join(x for x in [stop.get("city"), stop.get("country")] if x)
        if location:
            label = f"{label} ({location})"
        return {"label": label, "lat": lat, "lng": lng}

    def _order_route_stops(
        self,
        origin: dict,
        destination: Optional[dict],
        stops: list[tuple[dict, dict]],
        travel_mode: str,
    ) -> list[tuple[dict, dict]]:
        remaining = list(stops)
        ordered = []
        current = origin
        while remaining:
            next_item = min(
                remaining,
                key=lambda item: (
                    self._route_distance_score(current, item[1], travel_mode)
                    + (
                        self._route_distance_score(item[1], destination, travel_mode) * 0.15
                        if destination else 0
                    )
                ),
            )
            ordered.append(next_item)
            remaining.remove(next_item)
            current = next_item[1]
        return ordered

    def _route_distance_score(self, start: Optional[dict], end: Optional[dict], travel_mode: str) -> float:
        if not start or not end:
            return 0
        return self._estimate_travel_leg(start, end, travel_mode)["time_hours"]

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
        rows = self.lead_repo.conn.execute(
            """
            SELECT id
            FROM trip_plan_stops
            WHERE plan_id = ? AND archived_at IS NULL
            ORDER BY sequence_no ASC, created_at ASC
            """,
            (plan_id,),
        ).fetchall()
        for sequence_no, row in enumerate(rows, start=1):
            self.lead_repo.conn.execute(
                """
                UPDATE trip_plan_stops
                SET sequence_no = ?, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE id = ?
                """,
                (sequence_no, timestamp, actor_id, row["id"]),
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

    def _sync_trip_followup_activity(self, stop: dict, actor_id: str) -> None:
        if not stop.get("lead_id") or stop.get("result_status") != "Follow-up Needed":
            return

        next_action = (stop.get("visit_next_action") or stop.get("result_notes") or "").strip()
        if not next_action:
            return

        due_date = stop.get("visit_followup_due_date") or stop.get("planned_end_date") or stop.get("planned_date")
        payload = json.dumps(
            {
                "method": "Trip Visit",
                "content": next_action,
                "status": "pending",
                "next_action": next_action,
                "next_action_date": due_date,
                "source": "trip_visit_execution",
                "trip_plan_id": stop.get("plan_id"),
                "trip_stop_id": stop.get("id"),
            },
            ensure_ascii=False,
        )
        summary = f"Trip follow-up: {next_action}"[:200]

        if stop.get("followup_activity_id"):
            self.lead_repo.conn.execute(
                """
                UPDATE lead_activities
                SET summary = ?, payload_json = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (summary, payload, stop["followup_activity_id"]),
            )
            return

        activity_id = generate_uuid()
        self.lead_repo.conn.execute(
            """
            INSERT INTO lead_activities (
                id, lead_id, actor_id, action_type, visibility,
                is_formal_follow_up, summary, payload_json,
                changed_field, before_value, after_value, created_at
            ) VALUES (?, ?, ?, 'follow_up', 'all', 1, ?, ?, NULL, NULL, NULL, ?)
            """,
            (activity_id, stop["lead_id"], actor_id, summary, payload, now_iso()),
        )
        self.lead_repo.conn.execute(
            """
            UPDATE trip_plan_stops
            SET followup_activity_id = ?, updated_at = ?, updated_by = ?,
                row_version = row_version + 1
            WHERE id = ?
            """,
            (activity_id, now_iso(), actor_id, stop["id"]),
        )

        lead = self.lead_repo.get_by_id(stop["lead_id"])
        if lead:
            updates = {}
            if lead.get("sales_stage") in {"New", "Assigned"}:
                updates["sales_stage"] = "Following"
            if due_date:
                current_due = lead.get("next_followup_date")
                if not current_due or str(due_date) < str(current_due):
                    updates["next_followup_date"] = due_date
            if updates:
                assignments = ", ".join(f"{key} = ?" for key in updates)
                self.lead_repo.conn.execute(
                    f"""
                    UPDATE leads
                    SET {assignments}, updated_at = ?, updated_by = ?,
                        row_version = row_version + 1
                    WHERE id = ? AND archived_at IS NULL
                    """,
                    (*updates.values(), now_iso(), actor_id, stop["lead_id"]),
                )

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
            "address": group.get("address"),
            "lead_count": len(group["leads"]),
            "latest_lead_id": group["leads"][0]["id"] if group["leads"] else None,
        }
