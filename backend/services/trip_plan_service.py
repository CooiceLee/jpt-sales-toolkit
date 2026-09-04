from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from typing import Optional

from ..repositories.base import generate_uuid, now_iso
from .trip_leg_contract import normalize_priority, validate_time_windows
from .trip_leg_repository import TripLegRepository
from .trip_member_repository import TripMemberRepository
from . import trip_team_export as team_export
from .trip_team_adapter import (
    calculate_team_itinerary,
    persist_team_itinerary,
    suggest_team_visits,
)
from .trip_free_stop_repository import FREE_STOP_CATEGORIES, TripFreeStopRepository
from .trip_plan_invalidation import (
    clear_locked_overrides_for_stops,
    clear_locked_overrides_for_free_stops,
    invalidate_trip_plan_ids,
    stale_itinerary_summary,
)
from .trip_visit_briefing_repository import (
    TripVisitBriefingRepository,
    location_route_signature,
    normalize_payload as normalize_briefing_payload,
)
from .trip_transport_suggestions import get_transport_suggestion_service
from .trip_transport_suggestions.route_adapter import requests_from_preview
from .trip_export_html import render_trip_html
from .trip_export_ics import render_trip_ics
from .trip_export_working import build_working_model
from .trip_export_working_xlsx import render_working_xlsx
from .trip_export_model import (
    FULL_VARIANT, SHARED_VARIANT, build_trip_export_model,
)
from .trip_export_visit import (
    CHANNEL_PARTNER_COMPANIONS_HEADER,
    CUSTOMER_PERSONNEL_HEADER,
    formal_visit_row,
)
from .trip_export_xlsx import render_trip_xlsx

# A visit records whether a sample and whether a quote are needed. Neither has
# to be answered, so the stored value has three states and every place that
# prints one has to be able to say so.
ANSWER_TEXT = {None: "未填写 / Not answered", 1: "是 / Yes", 0: "否 / No"}

# Once somebody says a visit happened, when it happened is part of saying it.
RESULT_STATUS_NEEDING_ACTUAL_TIME = ("Visited", "Follow-up Needed")

# What a visit records about how it went. Editing any of these is reporting on
# the visit, so the rule above applies to all of them and not only to the
# status - a caller that sends just the fields it changed must not be able to
# report a result while leaving out when it happened.
EXECUTION_RESULT_FIELDS = (
    "result_status", "result_notes",
    "actual_visit_date", "actual_visit_period",
    "visit_customer_needs", "visit_competitor", "visit_budget",
    "visit_decision_maker", "visit_next_action", "visit_followup_due_date",
    "visit_sample_needed", "visit_quote_needed",
)


def _answer_text(value) -> str:
    return ANSWER_TEXT[None if value is None else int(bool(value))]


def _answer_value(value):
    """The stored answer as JSON sees it: unanswered, yes or no."""
    return None if value is None else bool(value)


def _participant_ids(rows) -> frozenset:
    """Who attends, as a set: the same people in another order is no change."""
    return frozenset(
        str(row.get("user_id")) for row in (rows or []) if row.get("user_id")
    )


def _participant_ids_json(value) -> str:
    """Which team members attend a free stop. Empty means everybody on the trip."""
    ids = [str(item).strip() for item in (value or []) if str(item).strip()]
    return json.dumps(list(dict.fromkeys(ids)), ensure_ascii=False)


def _visit_end(start_date, start_period, half_days: int):
    """Where a visit ends, counted in half-days from where it starts."""
    try:
        day = date.fromisoformat(str(start_date))
    except (TypeError, ValueError):
        return None
    if not day:
        return None
    period = "PM" if start_period == "PM" else "AM"
    for _ in range(max(1, half_days) - 1):
        if period == "AM":
            period = "PM"
        else:
            day, period = day + timedelta(days=1), "AM"
    return day.isoformat(), period


PLANNING_MODES = ("team",)


def _planning_mode(value) -> str:
    """There is one way to plan a trip: as a team, of one person or of six.

    Two ways meant two of everything to keep in step and a reader who had to
    know which one they were looking at. Anything else that arrives - an older
    client, a plan from before - is read as a team.
    """
    return "team"


def _md_separator(headers: list, right_align=frozenset()) -> str:
    """The rule under a Markdown header, always the same width as the header."""
    return "|" + "|".join(
        "---:" if header in right_align else "---" for header in headers
    ) + "|"


class TripPlanService:
    """Extracted ReviewService component."""

    def __init__(self, core):
        self.core = core
        self.leg_repo = TripLegRepository(core.lead_repo.conn)
        self.free_stop_repo = TripFreeStopRepository(core.lead_repo.conn)
        self.briefing_repo = TripVisitBriefingRepository(core.lead_repo.conn)
        self.member_repo = TripMemberRepository(core.lead_repo.conn)
        self.transport_suggestions = get_transport_suggestion_service()

    @staticmethod
    def _stale_itinerary_summary(reason: str, timestamp: str) -> str:
        return stale_itinerary_summary(reason, timestamp)

    def _invalidate_trip_itinerary(
        self,
        plan_id: str,
        actor_id: str,
        reason: str,
        timestamp: str,
    ) -> None:
        self.leg_repo.archive_active(plan_id, actor_id, timestamp)
        for table in ("trip_plan_stops", "trip_plan_free_stops"):
            self.core.lead_repo.conn.execute(
                f"""
                UPDATE {table}
                SET confirmation_status = 'needs_reconfirmation',
                    updated_at = ?, updated_by = ?, row_version = row_version + 1
                WHERE plan_id = ? AND archived_at IS NULL
                  AND confirmation_status = 'confirmed'
                  -- A visit whose time the customer agreed to does not move
                  -- when the route around it changes, so the confirmation still
                  -- stands. Asking for it again after every added stop trains
                  -- people to ignore the flag.
                  AND schedule_locked = 0
                """,
                (timestamp, actor_id, plan_id),
            )
        self.core.lead_repo.conn.execute(
            """
            UPDATE trip_plans
            SET itinerary_generated_at = NULL,
                itinerary_summary = CASE
                    WHEN itinerary_summary IS NOT NULL OR itinerary_generated_at IS NOT NULL
                    THEN ? ELSE NULL
                END,
                updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ?
            """,
            (self._stale_itinerary_summary(reason, timestamp), timestamp, actor_id, plan_id),
        )

    @staticmethod
    def _assert_itinerary_exportable(plan: dict) -> None:
        summary = plan.get("itinerary_summary") or {}
        if summary.get("stale") is True or summary.get("valid") is False:
            raise ValueError(
                "This itinerary is out of date; preview and save the route again before exporting"
            )

    @staticmethod
    def _trip_leg_confirmation(leg: dict) -> str:
        manual_values = any(
            leg.get(key) is not None
            for key in (
                "manual_distance_km",
                "manual_time_hours",
                "manual_travel_days",
                "manual_travel_half_days",
            )
        )
        if manual_values and leg.get("mode_locked"):
            return "manual_values_locked"
        if leg.get("mode_locked"):
            return "mode_locked_metrics_estimated"
        return "heuristic_estimate_confirm_manually"

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
        """Return scored customer candidates for trip planning."""
        limit = max(1, min(int(limit or 100), 200))
        offset = max(0, int(offset or 0))
        map_data = self.core.get_map_data(
            actor_id,
            actor_role,
            sales_stage=sales_stage,
            owner_id=owner_id,
            region=region,
        )

        candidates = []
        for point in map_data.get("points", []):
            if country and self.core._normalize_country(point.get("country")) != self.core._normalize_country(country):
                continue
            candidates.append(self.core._trip_candidate_from_point(point, missing_location=False))

        for item in map_data.get("missing_locations", []):
            if country and self.core._normalize_country(item.get("country")) != self.core._normalize_country(country):
                continue
            candidates.append(self.core._trip_candidate_from_missing(item))

        candidates.sort(key=lambda item: (item["score"], item["pipeline_value"], item["open_count"]), reverse=True)
        total = len(candidates)
        page = candidates[offset:offset + limit]
        return {
            "filters": {
                "region": region,
                "country": country,
                "owner_id": owner_id,
                "sales_stage": sales_stage,
            },
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total,
            },
            "summary": {
                "candidates": total,
                "exact_coordinates": sum(1 for item in candidates if item["coordinate_quality"] == "exact"),
                "needs_coordinate_review": sum(1 for item in candidates if item["needs_coordinate_review"]),
                "open_leads": sum(item["open_count"] for item in candidates),
                "pipeline_value": sum(item["pipeline_value"] for item in candidates),
            },
            "candidates": page,
        }

    def list_trip_plans(self, actor_id: str, actor_role: str) -> list[dict]:
        """List saved trip plans visible to the current user."""
        conn = self.core.lead_repo.conn
        sql = """
            SELECT p.*, u.display_name AS owner_name,
                   (
                       SELECT COUNT(*) FROM trip_plan_stops s
                       WHERE s.plan_id = p.id AND s.archived_at IS NULL
                   ) + (
                       SELECT COUNT(*) FROM trip_plan_free_stops fs
                       WHERE fs.plan_id = p.id AND fs.archived_at IS NULL
                   ) AS stop_count
            FROM trip_plans p
            LEFT JOIN users u ON p.owner_id = u.id
            WHERE p.archived_at IS NULL
        """
        params: list = []
        if actor_role != "leader":
            sql += " AND p.owner_id = ?"
            params.append(actor_id)
        sql += " ORDER BY p.updated_at DESC"
        return [self.core._normalize_trip_plan_row(dict(row)) for row in conn.execute(sql, params).fetchall()]

    def create_trip_plan(self, data: dict, actor_id: str) -> dict:
        """Create a new trip plan."""
        conn = self.core.lead_repo.conn
        now = now_iso()
        plan_id = generate_uuid()
        owner_id = data.get("owner_id") or actor_id
        prepared = self.core._prepare_trip_plan_data(data)
        conn.execute(
            """
            INSERT INTO trip_plans (
                id, title, owner_id, start_date, end_date, region,
                origin_name, origin_lat, origin_lng, destination_name,
                destination_lat, destination_lng, travel_mode,
                route_order_mode, transport_mode_priority,
                departure_window_start, departure_window_end,
                return_window_start, return_window_end,
                avoid_weekends, holiday_dates, description, status,
                planning_mode,
                created_at, created_by, updated_at, updated_by
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                plan_id,
                data.get("title") or "Untitled Trip Plan",
                owner_id,
                prepared.get("start_date"),
                prepared.get("end_date"),
                prepared.get("region"),
                prepared.get("origin_name"),
                prepared.get("origin_lat"),
                prepared.get("origin_lng"),
                prepared.get("destination_name"),
                prepared.get("destination_lat"),
                prepared.get("destination_lng"),
                prepared.get("travel_mode") or "auto",
                prepared.get("route_order_mode") or "auto",
                prepared.get("transport_mode_priority")
                or json.dumps(normalize_priority(None, prepared.get("travel_mode"))),
                prepared.get("departure_window_start"),
                prepared.get("departure_window_end"),
                prepared.get("return_window_start"),
                prepared.get("return_window_end"),
                prepared.get("avoid_weekends", 1),
                prepared.get("holiday_dates"),
                prepared.get("description"),
                data.get("status") or "Draft",
                _planning_mode(data.get("planning_mode")),
                now,
                actor_id,
                now,
                actor_id,
            ),
        )
        # A new trip already has one traveller: whoever it belongs to. The
        # planner needs somebody to move, and asking the reader to add
        # themselves before anything works is a step that explains nothing.
        conn.execute(
            "INSERT INTO trip_plan_members (id, plan_id, user_id, created_at, "
            "created_by, updated_at, updated_by, row_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (generate_uuid(), plan_id, owner_id, now, actor_id, now, actor_id),
        )
        conn.commit()
        return self.core.get_trip_plan(plan_id, actor_id, "leader") or {"id": plan_id}

    def get_trip_plan(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[dict]:
        """Get a trip plan with stops."""
        conn = self.core.lead_repo.conn
        plan = conn.execute(
            """
            SELECT p.*, u.display_name AS owner_name
            FROM trip_plans p
            LEFT JOIN users u ON p.owner_id = u.id
            WHERE p.id = ? AND p.archived_at IS NULL
            """,
            (plan_id,),
        ).fetchone()
        if not plan:
            return None
        plan_data = self.core._normalize_trip_plan_row(dict(plan))
        if not self.core._can_access_plan(plan_data, actor_id, actor_role):
            return None

        stops = conn.execute(
            """
            SELECT s.*, c.display_name AS customer_name, c.country, c.city,
                   c.postal_code, c.address, c.region, c.lat, c.lng, c.geocode_source,
                   c.geocode_confidence, c.geocode_locked,
                   (
                       SELECT cc.name FROM customer_contacts cc
                       WHERE cc.customer_id = c.id AND cc.archived_at IS NULL
                       ORDER BY cc.is_primary DESC, cc.created_at ASC
                       LIMIT 1
                   ) AS contact_name,
                   (
                       SELECT cc.position FROM customer_contacts cc
                       WHERE cc.customer_id = c.id AND cc.archived_at IS NULL
                       ORDER BY cc.is_primary DESC, cc.created_at ASC
                       LIMIT 1
                   ) AS contact_position,
                   (
                       SELECT cc.email FROM customer_contacts cc
                       WHERE cc.customer_id = c.id AND cc.archived_at IS NULL
                       ORDER BY cc.is_primary DESC, cc.created_at ASC
                       LIMIT 1
                   ) AS contact_email,
                   (
                       SELECT cc.phone FROM customer_contacts cc
                       WHERE cc.customer_id = c.id AND cc.archived_at IS NULL
                       ORDER BY cc.is_primary DESC, cc.created_at ASC
                       LIMIT 1
                   ) AS contact_phone,
                   (
                       SELECT cc.whatsapp FROM customer_contacts cc
                       WHERE cc.customer_id = c.id AND cc.archived_at IS NULL
                       ORDER BY cc.is_primary DESC, cc.created_at ASC
                       LIMIT 1
                   ) AS contact_whatsapp,
                   l.display_id AS lead_display_id, l.title AS lead_title,
                   l.sales_stage, l.estimated_value, l.deal_amount,
                   l.product_category, l.product_series, l.power_range,
                   l.wavelength, l.application, l.material, l.quantity_text,
                   l.quotation_id, l.po_number,
                   lu.display_name AS lead_owner_name
            FROM trip_plan_stops s
            JOIN customers c ON s.customer_id = c.id
            LEFT JOIN leads l ON s.lead_id = l.id
            LEFT JOIN users lu ON l.owner_id = lu.id
            WHERE s.plan_id = ? AND s.archived_at IS NULL
            ORDER BY s.sequence_no ASC, s.created_at ASC
            """,
            (plan_id,),
        ).fetchall()
        customer_stops = []
        for row in stops:
            item = dict(row)
            item["stop_kind"] = "customer"
            briefing = self.briefing_repo.decode(
                self.briefing_repo.get_row(item["id"])
            )
            item["briefing"] = briefing
            item["visit_location"] = self.briefing_repo.effective_location(
                item, briefing
            )
            customer_stops.append(item)
        plan_data["stops"] = sorted(
            [*customer_stops, *self.free_stop_repo.list_active(plan_id)],
            key=lambda item: (
                item.get("sequence_no") or 0,
                item.get("created_at") or "",
                item.get("id") or "",
            ),
        )
        summary = plan_data.get("itinerary_summary") or {}
        is_stale = summary.get("stale") is True or summary.get("valid") is False
        plan_data["members"] = self.member_repo.list_active(plan_id)
        if plan_data.get("planning_mode") == "team":
            # Who could be added to the trip. Only team planning needs it, so
            # legacy plans are not made to carry the account list.
            plan_data["available_members"] = (
                self.briefing_repo.available_participants(actor_id)
            )
        plan_data["legs"] = [] if is_stale else self.leg_repo.list_active(plan_id)
        plan_data["schedule_items"] = (
            [] if is_stale else list(summary.get("schedule_items") or [])
        )
        return plan_data

    def update_trip_plan(self, plan_id: str, data: dict, actor_id: str, actor_role: str) -> Optional[dict]:
        """Update trip plan header fields."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        expected_version = data.pop("row_version", None)
        self.core._assert_row_version(plan, expected_version)

        for required_key in (
            "title",
            "owner_id",
            "status",
            "avoid_weekends",
            "route_order_mode",
            "transport_mode_priority",
        ):
            if required_key in data and data[required_key] is None:
                raise ValueError(f"{required_key} cannot be null")

        window_keys = (
            "departure_window_start",
            "departure_window_end",
            "return_window_start",
            "return_window_end",
        )
        validate_time_windows(
            {key: data[key] if key in data else plan.get(key) for key in window_keys}
        )

        allowed = {
            "title",
            "start_date",
            "end_date",
            "region",
            "description",
            "status",
            "owner_id",
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
        update_data = self.core._prepare_trip_plan_data({key: value for key, value in data.items() if key in allowed})
        if not update_data:
            return plan

        if actor_role != "leader":
            update_data.pop("owner_id", None)

        now = now_iso()
        route_fields = {
            "start_date",
            "end_date",
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
        route_stale = bool(route_fields.intersection(update_data))
        if route_stale and (
            plan.get("itinerary_summary") is not None
            or plan.get("itinerary_generated_at")
        ):
            update_data["itinerary_generated_at"] = None
            update_data["itinerary_summary"] = self._stale_itinerary_summary(
                "route_settings_changed", now
            )

        update_data["updated_at"] = now
        update_data["updated_by"] = actor_id
        update_data["row_version"] = int(plan.get("row_version") or 1) + 1
        assignments = ", ".join(f"{key} = ?" for key in update_data)
        params = [*update_data.values(), plan_id]
        where = "id = ?"
        if expected_version is not None:
            where += " AND row_version = ?"
            params.append(expected_version)
        conn = self.core.lead_repo.conn
        try:
            cursor = conn.execute(
                f"UPDATE trip_plans SET {assignments} WHERE {where}",
                tuple(params),
            )
            if cursor.rowcount == 0:
                current = self.core.get_trip_plan(plan_id, actor_id, actor_role)
                if current:
                    self.core._assert_row_version(current, expected_version)
            elif route_stale:
                self.leg_repo.archive_active(plan_id, actor_id, now)
                for table in ("trip_plan_stops", "trip_plan_free_stops"):
                    conn.execute(
                        f"""
                        UPDATE {table}
                        SET confirmation_status = 'needs_reconfirmation',
                            updated_at = ?, updated_by = ?, row_version = row_version + 1
                        WHERE plan_id = ? AND archived_at IS NULL
                          AND confirmation_status = 'confirmed'
                          AND schedule_locked = 0
                        """,
                        (now, actor_id, plan_id),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def _require_actual_visit_time(self, current: dict, update_data: dict) -> None:
        """A visit reported as done has to say when it actually happened.

        Stops already saved as done before this rule existed are left alone
        until somebody reports on them again - refusing to open them would make
        history unreachable rather than complete. Reporting means touching any
        of the fields that describe how the visit went, not only its status:
        a caller that sends only what changed must not be able to edit a result
        while leaving out when it happened.
        """
        status = update_data.get("result_status", current.get("result_status"))
        if status not in RESULT_STATUS_NEEDING_ACTUAL_TIME:
            return
        if not any(key in update_data for key in EXECUTION_RESULT_FIELDS):
            return
        date = update_data.get("actual_visit_date", current.get("actual_visit_date"))
        period = update_data.get(
            "actual_visit_period", current.get("actual_visit_period")
        )
        if not date or not period:
            raise ValueError(
                f"A visit saved as {status} needs the date and the half-day it "
                "actually happened on"
            )

    def _briefing_suggestions(self, stop: dict) -> dict:
        equipment = []
        demo_text = " / ".join(
            str(value) for value in (
                stop.get("product_series"), stop.get("power_range"),
                stop.get("wavelength"), stop.get("application"),
            ) if value
        )
        if demo_text:
            equipment.append(
                {
                    "kind": "demo",
                    "model": stop.get("product_series"),
                    "specification": demo_text,
                    "quantity": stop.get("quantity_text"),
                    "owner_team": None,
                    "notes": None,
                    "sequence_no": 1,
                }
            )
        if stop.get("po_number"):
            equipment.append(
                {
                    "kind": "po",
                    "model": stop.get("product_series"),
                    "specification": stop.get("po_number"),
                    "quantity": stop.get("quantity_text"),
                    "owner_team": None,
                    "notes": None,
                    "sequence_no": len(equipment) + 1,
                }
            )
        agenda = []
        for topic in (
            stop.get("visit_purpose"),
            stop.get("lead_title"),
            stop.get("application"),
        ):
            if topic and topic not in {item["topic"] for item in agenda}:
                agenda.append(
                    {
                        "topic": topic,
                        "owner": None,
                        "preparation": None,
                        "expected_outcome": None,
                        "sequence_no": len(agenda) + 1,
                    }
                )
        return {
            "equipment": equipment,
            "agenda_items": agenda,
            "lead": {
                key: stop.get(key)
                for key in (
                    "lead_id", "lead_display_id", "lead_title", "product_category",
                    "product_series", "power_range", "wavelength", "application",
                    "material", "quantity_text", "quotation_id", "po_number",
                )
            },
        }

    def _briefing_participants(self, plan: dict, actor_id: str) -> list:
        """Who can be put on this visit.

        On a team trip that is the people travelling, not the account list: the
        directory offers colleagues who are not on this trip, and naming one is
        not a visit anybody attends. A single-traveller plan has no team, so the
        directory is the only list there is.
        """
        directory = self.briefing_repo.available_participants(actor_id)
        if plan.get("planning_mode") != "team":
            return directory
        travelling = {
            member["user_id"]
            for member in self.member_repo.list_active(plan["id"])
        }
        return [
            person for person in directory
            if str(person.get("user_id") or person.get("id")) in travelling
        ]

    def _briefing_response(
        self, stop: dict, briefing: dict, actor_id: str, plan: dict
    ) -> dict:
        return {
            **briefing,
            "stop_id": stop["id"],
            "stop_row_version": int(stop.get("row_version") or 1),
            "confirmation_status": stop.get("confirmation_status") or "unconfirmed",
            "available_contacts": self.briefing_repo.available_contacts(
                stop["customer_id"]
            ),
            "available_participants": self._briefing_participants(
                plan, actor_id
            ),
            "suggestions": self._briefing_suggestions(stop),
            "effective_location": self.briefing_repo.effective_location(stop, briefing),
        }

    def get_trip_visit_briefing(
        self,
        plan_id: str,
        stop_id: str,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        stop = next(
            (
                item for item in plan.get("stops", [])
                if item.get("id") == stop_id and item.get("stop_kind") == "customer"
            ),
            None,
        )
        if not stop:
            return None
        briefing = self.briefing_repo.decode(self.briefing_repo.get_row(stop_id))
        return self._briefing_response(stop, briefing, actor_id, plan)

    def put_trip_visit_briefing(
        self,
        plan_id: str,
        stop_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        current = self.core._get_trip_stop(stop_id)
        if not current or current.get("plan_id") != plan_id:
            return None
        if "stop_row_version" not in data:
            raise ValueError("stop_row_version is required")
        expected_stop_version = int(data["stop_row_version"])
        self.core._assert_row_version(current, expected_stop_version)

        payload = normalize_briefing_payload(data)
        self.briefing_repo.validate_snapshots(
            current["customer_id"], payload["contacts"], payload["participants"],
            actor_id,
        )
        existing_row = self.briefing_repo.get_row(stop_id)
        existing = self.briefing_repo.decode(existing_row)
        location_changed = location_route_signature(
            existing["location"]
        ) != location_route_signature(payload["location"])
        # Who goes decides the route in team planning: change the attendees and
        # the legs, the merges, the travel time and the lanes all change with
        # them. Order does not matter, membership does.
        attendees_changed = (
            plan.get("planning_mode") == "team"
            and _participant_ids(existing.get("participants"))
            != _participant_ids(payload.get("participants"))
        )
        route_changed = location_changed or attendees_changed
        next_status = payload["confirmation_status"]
        if location_changed and next_status == "confirmed":
            next_status = "needs_reconfirmation"

        conn = self.core.lead_repo.conn
        timestamp = now_iso()
        savepoint = "trip_visit_briefing_put"
        owns_transaction = not conn.in_transaction
        try:
            if owns_transaction:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute(f"SAVEPOINT {savepoint}")
            cursor = conn.execute(
                """
                UPDATE trip_plan_stops
                SET confirmation_status = ?, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE id = ? AND plan_id = ? AND archived_at IS NULL
                  AND row_version = ?
                """,
                (
                    next_status,
                    timestamp,
                    actor_id,
                    stop_id,
                    plan_id,
                    expected_stop_version,
                ),
            )
            if cursor.rowcount != 1:
                latest = self.core._get_trip_stop(stop_id) or {}
                raise ConflictError(
                    int(latest.get("row_version") or 0),
                    expected_stop_version,
                    {"id": stop_id, "updated_at": latest.get("updated_at")},
                )
            self.briefing_repo.replace(
                stop_id,
                payload,
                actor_id,
                timestamp,
                data.get("row_version"),
            )
            if route_changed:
                if location_changed:
                    clear_locked_overrides_for_stops(
                        conn, [stop_id], actor_id, timestamp
                    )
                invalidate_trip_plan_ids(
                    conn,
                    [plan_id],
                    actor_id,
                    "visit_location_changed" if location_changed
                    else "visit_attendees_changed",
                    timestamp=timestamp,
                )
            if owns_transaction:
                conn.commit()
            else:
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        except Exception:
            if owns_transaction:
                conn.rollback()
            else:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise

        updated = self.core._get_trip_stop(stop_id)
        briefing = self.briefing_repo.decode(self.briefing_repo.get_row(stop_id))
        return (
            self._briefing_response(updated, briefing, actor_id, plan)
            if updated else None
        )

    def archive_trip_plan(
        self,
        plan_id: str,
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> bool:
        """Archive a trip plan."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return False
        self.core._assert_row_version(plan, row_version)
        now = now_iso()
        params = [now, now, actor_id, plan_id]
        where = "id = ?"
        if row_version is not None:
            where += " AND row_version = ?"
            params.append(row_version)
        cursor = self.core.lead_repo.conn.execute(
            f"""
            UPDATE trip_plans
            SET archived_at = ?, updated_at = ?, updated_by = ?,
                row_version = row_version + 1
            WHERE {where}
            """,
            tuple(params),
        )
        if cursor.rowcount == 0:
            latest = self.core.get_trip_plan(plan_id, actor_id, actor_role)
            if latest:
                self.core._assert_row_version(latest, row_version)
        self.core.lead_repo.conn.commit()
        return cursor.rowcount > 0

    def add_trip_stop(self, plan_id: str, data: dict, actor_id: str, actor_role: str) -> Optional[dict]:
        """Add a customer or lead stop to a trip plan."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None

        allow_duplicate = bool(data.pop("allow_duplicate", False))
        lead_id = data.get("lead_id")
        customer_id = data.get("customer_id")
        if lead_id:
            lead = self.core._visible_lead_by_id(lead_id, actor_id, actor_role)
            if not lead:
                raise ValueError("Lead is not visible or does not exist")
            customer_id = lead["customer_id"]
        elif customer_id and not self.core._can_access_customer(customer_id, actor_id, actor_role):
            raise ValueError("Customer is not visible or does not exist")
        elif not customer_id:
            raise ValueError("customer_id or lead_id is required")

        conn = self.core.lead_repo.conn
        customer = conn.execute(
            """
            SELECT id, lat, lng
            FROM customers
            WHERE id = ? AND archived_at IS NULL
            """,
            (customer_id,),
        ).fetchone()
        if (
            not customer
            or self.core._finite_float(customer["lat"]) is None
            or self.core._finite_float(customer["lng"]) is None
        ):
            raise ValueError(
                "Customer needs saved latitude and longitude before it can be added to a trip plan"
            )

        if not allow_duplicate:
            duplicate = conn.execute(
                """
                SELECT id
                FROM trip_plan_stops
                WHERE plan_id = ? AND archived_at IS NULL
                  AND (customer_id = ? OR (? IS NOT NULL AND lead_id = ?))
                LIMIT 1
                """,
                (plan_id, customer_id, lead_id, lead_id),
            ).fetchone()
            if duplicate:
                raise ValueError(
                    "This customer or lead is already in the trip plan; set allow_duplicate=true to add another visit"
                )

        next_sequence = self.free_stop_repo.next_sequence(plan_id)
        desired_sequence = int(data.get("sequence_no") or next_sequence)
        if desired_sequence < 1 or desired_sequence > next_sequence:
            raise ValueError(
                f"sequence_no must be between 1 and {next_sequence}"
            )
        now = now_iso()
        stop_id = generate_uuid()
        if data.get("duration_half_days") is not None and data.get("stay_days") is not None:
            raise ValueError(
                "Choose either a half-day visit duration or a full-day stay, not both"
            )
        duration_half_days = int(
            data.get("duration_half_days")
            or self.core._clean_stay_days(data.get("stay_days")) * 2
        )
        stay_days = (duration_half_days + 1) // 2
        try:
            conn.execute(
                """
                INSERT INTO trip_plan_stops (
                    id, plan_id, customer_id, lead_id, sequence_no, planned_date,
                    planned_end_date, planned_start_period, planned_end_period,
                    duration_half_days, stay_days, preferred_period, schedule_locked,
                    confirmation_status, visit_purpose, notes, result_status,
                    created_at, created_by, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'Planned', ?, ?, ?, ?)
                """,
                (
                    stop_id,
                    plan_id,
                    customer_id,
                    lead_id,
                    next_sequence,
                    data.get("planned_date"),
                    data.get("planned_end_date"),
                    data.get("planned_start_period"),
                    data.get("planned_end_period"),
                    duration_half_days,
                    stay_days,
                    data.get("preferred_period") or "auto",
                    1 if data.get("schedule_locked") else 0,
                    data.get("confirmation_status") or "unconfirmed",
                    data.get("visit_purpose"),
                    data.get("notes"),
                    now,
                    actor_id,
                    now,
                    actor_id,
                ),
            )
            if desired_sequence != next_sequence:
                ordered_ids = [
                    row["id"] for row in self.free_stop_repo.active_references(plan_id)
                    if row["id"] != stop_id
                ]
                ordered_ids.insert(desired_sequence - 1, stop_id)
                self.free_stop_repo.set_order(plan_id, ordered_ids, actor_id, now)
            self._invalidate_trip_itinerary(plan_id, actor_id, "stop_added", now)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def add_trip_free_stop(
        self,
        plan_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        """Add a route stop without creating a customer or Lead."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        category = str(data.get("category") or "").strip().lower()
        location_name = str(data.get("location_name") or "").strip()
        if category not in FREE_STOP_CATEGORIES:
            raise ValueError("Unsupported free stop category")
        if not location_name:
            raise ValueError("location_name is required")
        lat = self.core._finite_float(data.get("lat"))
        lng = self.core._finite_float(data.get("lng"))
        if lat is None or not -90 <= lat <= 90:
            raise ValueError("lat must be between -90 and 90")
        if lng is None or not -180 <= lng <= 180:
            raise ValueError("lng must be between -180 and 180")

        conn = self.core.lead_repo.conn
        next_sequence = self.free_stop_repo.next_sequence(plan_id)
        desired_sequence = int(data.get("sequence_no") or next_sequence)
        if desired_sequence < 1 or desired_sequence > next_sequence:
            raise ValueError(
                f"sequence_no must be between 1 and {next_sequence}"
            )
        now = now_iso()
        free_stop_id = generate_uuid()
        if data.get("duration_half_days") is not None and data.get("stay_days") is not None:
            raise ValueError(
                "Choose either a half-day stop duration or a full-day stay, not both"
            )
        duration_half_days = int(
            data.get("duration_half_days")
            or self.core._clean_stay_days(data.get("stay_days")) * 2
        )
        stay_days = (duration_half_days + 1) // 2
        try:
            conn.execute(
                """
                INSERT INTO trip_plan_free_stops (
                    id, plan_id, category, location_name, address, city, country,
                    lat, lng, sequence_no, planned_date, planned_end_date,
                    planned_start_period, planned_end_period,
                    duration_half_days, stay_days, preferred_period, schedule_locked,
                    confirmation_status, visit_purpose, notes,
                    participant_user_ids_json,
                    created_at, created_by, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    free_stop_id,
                    plan_id,
                    category,
                    location_name,
                    data.get("address"),
                    data.get("city"),
                    data.get("country"),
                    lat,
                    lng,
                    next_sequence,
                    data.get("planned_date"),
                    data.get("planned_end_date"),
                    data.get("planned_start_period"),
                    data.get("planned_end_period"),
                    duration_half_days,
                    stay_days,
                    data.get("preferred_period") or "auto",
                    1 if data.get("schedule_locked") else 0,
                    data.get("confirmation_status") or "unconfirmed",
                    data.get("visit_purpose"),
                    data.get("notes"),
                    _participant_ids_json(data.get("participant_user_ids")),
                    now,
                    actor_id,
                    now,
                    actor_id,
                ),
            )
            if desired_sequence != next_sequence:
                ordered_ids = [
                    row["id"] for row in self.free_stop_repo.active_references(plan_id)
                    if row["id"] != free_stop_id
                ]
                ordered_ids.insert(desired_sequence - 1, free_stop_id)
                self.free_stop_repo.set_order(
                    plan_id, ordered_ids, actor_id, now
                )
            self._invalidate_trip_itinerary(plan_id, actor_id, "stop_added", now)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def update_trip_free_stop(
        self,
        plan_id: str,
        free_stop_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        """Update an independent route stop without Lead-side effects."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        current = self.free_stop_repo.get_active(free_stop_id)
        if not current or current["plan_id"] != plan_id:
            return None
        expected_version = data.pop("row_version", None)
        self.core._assert_row_version(current, expected_version)

        allowed = {
            "category", "location_name", "address", "city", "country",
            "lat", "lng", "planned_date", "planned_end_date",
            "planned_start_period", "planned_end_period",
            "stay_days", "duration_half_days", "preferred_period",
            "schedule_locked", "confirmation_status", "visit_purpose", "notes",
            "participant_user_ids",
        }
        update_data = {key: value for key, value in data.items() if key in allowed}
        if "participant_user_ids" in update_data:
            update_data["participant_user_ids_json"] = _participant_ids_json(
                update_data.pop("participant_user_ids")
            )
        for required_key in (
            "category", "location_name", "lat", "lng", "stay_days",
            "duration_half_days", "preferred_period", "schedule_locked",
            "confirmation_status",
        ):
            if required_key in update_data and update_data[required_key] is None:
                raise ValueError(f"{required_key} cannot be null")
        if "category" in update_data:
            update_data["category"] = str(update_data["category"]).strip().lower()
            if update_data["category"] not in FREE_STOP_CATEGORIES:
                raise ValueError("Unsupported free stop category")
        if "location_name" in update_data:
            update_data["location_name"] = str(update_data["location_name"]).strip()
            if not update_data["location_name"]:
                raise ValueError("location_name is required")
        for coordinate, lower, upper in (("lat", -90, 90), ("lng", -180, 180)):
            if coordinate in update_data:
                update_data[coordinate] = self.core._finite_float(update_data[coordinate])
                if (
                    update_data[coordinate] is None
                    or not lower <= update_data[coordinate] <= upper
                ):
                    raise ValueError(f"{coordinate} must be between {lower} and {upper}")
        if "stay_days" in update_data and "duration_half_days" in update_data:
            raise ValueError(
                "Choose either a half-day stop duration or a full-day stay, not both"
            )
        if "duration_half_days" in update_data:
            update_data["duration_half_days"] = int(update_data["duration_half_days"])
            update_data["stay_days"] = (update_data["duration_half_days"] + 1) // 2
        elif "stay_days" in update_data:
            update_data["stay_days"] = self.core._clean_stay_days(
                update_data["stay_days"]
            )
            update_data["duration_half_days"] = update_data["stay_days"] * 2
        for bool_key in ("schedule_locked",):
            if bool_key in update_data:
                update_data[bool_key] = 1 if update_data[bool_key] else 0

        requested_sequence = data.get("sequence_no")
        ordered_refs = self.free_stop_repo.active_references(plan_id)
        if requested_sequence is not None:
            requested_sequence = int(requested_sequence)
            if requested_sequence < 1 or requested_sequence > len(ordered_refs):
                raise ValueError(
                    f"sequence_no must be between 1 and {len(ordered_refs)}"
                )
        route_fields = {
                "location_name", "address", "city", "country", "lat", "lng",
                "planned_date", "planned_end_date", "planned_start_period",
                "planned_end_period", "stay_days", "duration_half_days",
                "preferred_period", "schedule_locked",
                # In team planning, who is at a stop decides whose route it is on.
                "participant_user_ids_json",
        }
        route_changed = requested_sequence is not None or any(
            key in update_data and update_data[key] != current.get(key)
            for key in route_fields
        )
        endpoint_identity_changed = any(
            key in update_data and update_data[key] != current.get(key)
            for key in (
                "category",
                "location_name",
                "address",
                "city",
                "country",
                "lat",
                "lng",
            )
        )
        if not update_data and requested_sequence is None:
            return plan

        conn = self.core.lead_repo.conn
        now = now_iso()
        try:
            if update_data:
                update_data["updated_at"] = now
                update_data["updated_by"] = actor_id
                update_data["row_version"] = int(current.get("row_version") or 1) + 1
                assignments = ", ".join(f"{key} = ?" for key in update_data)
                params = [*update_data.values(), free_stop_id, plan_id]
                where = "id = ? AND plan_id = ? AND archived_at IS NULL"
                if expected_version is not None:
                    where += " AND row_version = ?"
                    params.append(expected_version)
                cursor = conn.execute(
                    f"UPDATE trip_plan_free_stops SET {assignments} WHERE {where}",
                    tuple(params),
                )
                if cursor.rowcount == 0:
                    latest = self.free_stop_repo.get_active(free_stop_id)
                    if latest:
                        self.core._assert_row_version(latest, expected_version)
            if requested_sequence is not None:
                ordered_ids = [
                    row["id"] for row in ordered_refs if row["id"] != free_stop_id
                ]
                ordered_ids.insert(requested_sequence - 1, free_stop_id)
                self.free_stop_repo.set_order(plan_id, ordered_ids, actor_id, now)
                conn.execute(
                    "UPDATE trip_plans SET route_order_mode = 'manual' WHERE id = ?",
                    (plan_id,),
                )
            if endpoint_identity_changed:
                clear_locked_overrides_for_free_stops(
                    conn,
                    [free_stop_id],
                    actor_id,
                    now,
                )
            if route_changed:
                self._invalidate_trip_itinerary(
                    plan_id, actor_id, "stop_schedule_changed", now
                )
            else:
                conn.execute(
                    """
                    UPDATE trip_plans
                    SET updated_at = ?, updated_by = ?, row_version = row_version + 1
                    WHERE id = ?
                    """,
                    (now, actor_id, plan_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def update_trip_stop(
        self,
        plan_id: str,
        stop_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        """Update a trip stop and sync visit result back to Lead Activity."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        current = self.core._get_trip_stop(stop_id)
        if not current or current["plan_id"] != plan_id:
            return None
        expected_version = data.pop("row_version", None)
        self.core._assert_row_version(current, expected_version)
        # A suggestion is worked out from the whole plan, so applying one has to
        # check the plan has not moved on - another visit's time, who is
        # travelling, or who attends what would all make it wrong. Ordinary stop
        # edits do not send this and are unaffected.
        expected_plan_version = data.pop("plan_row_version", None)
        if expected_plan_version is not None:
            self.core._assert_row_version(plan, expected_plan_version)

        requested_sequence = data.pop("sequence_no", None)
        ordered_refs = self.free_stop_repo.active_references(plan_id)
        if requested_sequence is not None:
            requested_sequence = int(requested_sequence)
            if requested_sequence < 1 or requested_sequence > len(ordered_refs):
                raise ValueError(
                    f"sequence_no must be between 1 and {len(ordered_refs)}"
                )

        allowed = {
            "planned_date",
            "planned_end_date",
            "planned_start_period",
            "planned_end_period",
            "stay_days",
            "duration_half_days",
            "preferred_period",
            "schedule_locked",
            "planned_time_accepted",
            "confirmation_status",
            "visit_purpose",
            "notes",
            "result_status",
            "result_notes",
            "visit_customer_needs",
            "visit_competitor",
            "visit_budget",
            "visit_decision_maker",
            "visit_next_action",
            "visit_followup_due_date",
            "visit_sample_needed",
            "visit_quote_needed",
            "actual_visit_date",
            "actual_visit_period",
            "lead_id",
        }
        update_data = {key: value for key, value in data.items() if key in allowed}
        for required_key in ("result_status",):
            if required_key in update_data and update_data[required_key] is None:
                raise ValueError(f"{required_key} cannot be null")
        if "stay_days" in update_data and "duration_half_days" in update_data:
            raise ValueError(
                "Choose either a half-day visit duration or a full-day stay, not both"
            )
        if "duration_half_days" in update_data:
            update_data["duration_half_days"] = int(update_data["duration_half_days"])
            update_data["stay_days"] = (update_data["duration_half_days"] + 1) // 2
        elif "stay_days" in update_data:
            update_data["stay_days"] = self.core._clean_stay_days(update_data["stay_days"])
            update_data["duration_half_days"] = update_data["stay_days"] * 2
        if "schedule_locked" in update_data:
            update_data["schedule_locked"] = 1 if update_data["schedule_locked"] else 0
        # A visit's end follows from when it starts and how long it takes. When
        # only the start is given - which is what recording an agreed time
        # sends - the end has to move with it, or the stop keeps the end the
        # previous calculation left behind and reads as finishing before it
        # begins.
        if "planned_date" in update_data and "planned_end_date" not in update_data:
            half_days = int(
                update_data.get("duration_half_days")
                or current.get("duration_half_days")
                or 2
            )
            end = _visit_end(
                update_data["planned_date"],
                update_data.get("planned_start_period")
                or current.get("planned_start_period"),
                half_days,
            )
            if end:
                update_data["planned_end_date"] = end[0]
                update_data["planned_end_period"] = end[1]
        if "planned_time_accepted" in update_data:
            update_data["planned_time_accepted"] = (
                1 if update_data["planned_time_accepted"] else 0
            )
        for answer_key in ("visit_sample_needed", "visit_quote_needed"):
            if answer_key in update_data:
                # Nobody has to answer these. Sent as nothing they stay
                # unanswered, which is not the same as answering "no".
                value = update_data[answer_key]
                update_data[answer_key] = None if value is None else int(bool(value))
        self._require_actual_visit_time(current, update_data)
        if "lead_id" in update_data and update_data["lead_id"]:
            lead = self.core._visible_lead_by_id(update_data["lead_id"], actor_id, actor_role)
            if not lead or lead["customer_id"] != current["customer_id"]:
                raise ValueError("Lead is not visible or does not belong to this customer")

        should_sync_activity = any(
            key in data
            for key in (
                "result_status",
                "result_notes",
                "visit_customer_needs",
                "visit_competitor",
                "visit_budget",
                "visit_decision_maker",
                "visit_next_action",
                "visit_sample_needed",
                "visit_quote_needed",
                "actual_visit_date",
                "actual_visit_period",
            )
        )
        schedule_changed = requested_sequence is not None or any(
            key in update_data and update_data[key] != current.get(key)
            for key in (
                "sequence_no", "planned_date", "planned_end_date",
                "planned_start_period", "planned_end_period", "stay_days",
                "duration_half_days", "preferred_period", "schedule_locked",
            )
        )
        if update_data or should_sync_activity or requested_sequence is not None:
            conn = self.core.lead_repo.conn
            try:
                plan_updated_at = now_iso()
                if update_data:
                    update_data["updated_at"] = plan_updated_at
                    update_data["updated_by"] = actor_id
                    update_data["row_version"] = int(current.get("row_version") or 1) + 1
                    assignments = ", ".join(f"{key} = ?" for key in update_data)
                    params = [*update_data.values(), stop_id]
                    where = "id = ?"
                    if expected_version is not None:
                        where += " AND row_version = ?"
                        params.append(expected_version)
                    cursor = conn.execute(
                        f"UPDATE trip_plan_stops SET {assignments} WHERE {where}",
                        tuple(params),
                    )
                    if cursor.rowcount == 0:
                        latest = self.core._get_trip_stop(stop_id)
                        if latest:
                            self.core._assert_row_version(latest, expected_version)
                    if schedule_changed:
                        self._invalidate_trip_itinerary(
                            plan_id,
                            actor_id,
                            "stop_schedule_changed",
                            plan_updated_at,
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE trip_plans
                            SET updated_at = ?, updated_by = ?, row_version = row_version + 1
                            WHERE id = ?
                            """,
                            (plan_updated_at, actor_id, plan_id),
                        )

                if requested_sequence is not None:
                    ordered_ids = [
                        row["id"] for row in ordered_refs if row["id"] != stop_id
                    ]
                    ordered_ids.insert(requested_sequence - 1, stop_id)
                    self.free_stop_repo.set_order(
                        plan_id, ordered_ids, actor_id, plan_updated_at
                    )
                    conn.execute(
                        "UPDATE trip_plans SET route_order_mode = 'manual' WHERE id = ?",
                        (plan_id,),
                    )
                    if not update_data:
                        self._invalidate_trip_itinerary(
                            plan_id,
                            actor_id,
                            "stop_schedule_changed",
                            plan_updated_at,
                        )

                updated_stop = self.core._get_trip_stop(stop_id)
                if updated_stop and should_sync_activity:
                    self.core._sync_trip_result_activity(updated_stop, actor_id)
                if updated_stop:
                    self.core._sync_trip_followup_activity(
                        updated_stop,
                        actor_id,
                        previous_lead_id=current.get("lead_id"),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def reorder_trip_stops(
        self,
        plan_id: str,
        stop_ids: list[str],
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> Optional[dict]:
        """Reorder all active stops in a trip plan."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        self.core._assert_row_version(plan, row_version)

        active_ids = [stop["id"] for stop in plan.get("stops", [])]
        if len(stop_ids) != len(set(stop_ids)):
            raise ValueError("Duplicate stop IDs are not allowed")
        if set(stop_ids) != set(active_ids):
            raise ValueError("Reorder must include every active stop exactly once")

        conn = self.core.lead_repo.conn
        now = now_iso()
        try:
            self.free_stop_repo.set_order(plan_id, stop_ids, actor_id, now)
            conn.execute(
                "UPDATE trip_plans SET route_order_mode = 'manual' WHERE id = ?",
                (plan_id,),
            )
            self._invalidate_trip_itinerary(
                plan_id,
                actor_id,
                "stop_order_changed",
                now,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def generate_trip_itinerary(
        self,
        plan_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        """Generate a heuristic route and business-day schedule for a trip plan."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        expected_version = data.pop("row_version", None)
        self.core._assert_row_version(plan, expected_version)
        if "title" in data:
            title = str(data.get("title") or "").strip()
            if not title:
                raise ValueError("title cannot be empty")
            data["title"] = title
        return self._generate_team_itinerary(
            plan, data, actor_id, actor_role, expected_version
        )

    def suggest_trip_flexible_visits(
        self, plan_id: str, data: dict, actor_id: str, actor_role: str
    ) -> Optional[dict]:
        """Propose a time for each customer visit with none agreed.

        Nothing is written. The plan's version comes back with the suggestions
        so applying one can check the plan it was worked out from is still the
        plan being changed.
        """
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        if plan.get("planning_mode") != "team":
            raise ValueError(
                "Flexible visit suggestions are part of team planning"
            )
        suggestions = suggest_team_visits(self.core, self.member_repo, plan, data)
        return {
            "plan_id": plan_id,
            "plan_row_version": int(plan.get("row_version") or 1),
            "suggestions": suggestions,
        }

    def set_trip_member(self, plan_id: str, data: dict, actor_id: str,
                        actor_role: str) -> Optional[dict]:
        """Put a team account on the trip, or change where they travel from."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        user_id = str(data.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("user_id is required")
        member = self.member_repo.add(plan_id, user_id, data, actor_id)
        if member is None:
            raise ValueError(
                "Trip members must be active team accounts"
            )
        self._invalidate_trip_itinerary(
            plan_id, actor_id, "trip_team_changed", now_iso()
        )
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def remove_trip_member(self, plan_id: str, user_id: str, actor_id: str,
                           actor_role: str) -> Optional[dict]:
        """Take somebody off the trip; their calculated route goes with them."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        if not self.member_repo.remove(plan_id, user_id):
            return None
        self._invalidate_trip_itinerary(
            plan_id, actor_id, "trip_team_changed", now_iso()
        )
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def _generate_team_itinerary(
        self, plan: dict, data: dict, actor_id: str, actor_role: str,
        expected_version,
    ) -> Optional[dict]:
        """Save a team itinerary.

        A trip that runs past its end date is reported as a risk, not refused:
        with fixed appointments the dates are often the thing that has to give,
        and the planner's job is to show that, not to hide it.
        """
        plan_id = plan["id"]
        summary = calculate_team_itinerary(self.core, self.member_repo, plan, data)
        # Saving the route saves what the route was planned from. The dates, the
        # endpoints and the transport preferences arrive in the same request and
        # single-traveller planning has always written them; leaving them out
        # here is how a changed start date came back as the old one.
        plan_updates = self.core._prepare_trip_plan_data(
            {
                **data,
                "itinerary_generated_at": now_iso(),
                "itinerary_summary": summary,
            },
            include_system_fields=True,
        )
        conn = self.core.lead_repo.conn
        now = now_iso()
        try:
            persist_team_itinerary(self, plan_id, summary, actor_id, now)
            plan_updates["updated_at"] = now
            plan_updates["updated_by"] = actor_id
            plan_updates["row_version"] = int(plan.get("row_version") or 1) + 1
            assignments = ", ".join(f"{key} = ?" for key in plan_updates)
            conn.execute(
                f"""
                UPDATE trip_plans SET {assignments} WHERE id = ?
                """
                + (" AND row_version = ?" if expected_version is not None else ""),
                (
                    *plan_updates.values(), plan_id,
                    *([expected_version] if expected_version is not None else []),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def preview_trip_itinerary(
        self,
        plan_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
    ) -> Optional[dict]:
        """Preview a heuristic route and schedule without writing to the database."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        summary = calculate_team_itinerary(
            self.core, self.member_repo, plan, data
        )
        # The same shape a preview has always had. A caller that asked for a
        # preview is shown the route it would get, marked as not yet saved -
        # anything less and the page draws the previous route while reporting
        # the new one's totals.
        return self.core._trip_itinerary_preview_plan(
            plan,
            {
                "summary": summary,
                "stop_updates": summary.get("stop_updates") or [],
                "legs": summary.get("legs") or [],
            },
        )

    def get_trip_transport_suggestions(
        self,
        plan_id: str,
        data: dict,
        actor_id: str,
        actor_role: str,
        *,
        force_refresh: bool = False,
    ) -> Optional[dict]:
        """Suggest per-leg metrics from the zero-write itinerary preview."""
        preview = self.preview_trip_itinerary(plan_id, data, actor_id, actor_role)
        if preview is None:
            return None
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if plan is None:
            return None
        requests = requests_from_preview(self.core, plan, data, preview)
        suggestions = [
            self.transport_suggestions.suggest(item, force_refresh=force_refresh).as_dict()
            for item in requests
        ]
        summary = preview.get("itinerary_summary") or {}
        warnings = [str(item) for item in summary.get("warnings") or []]
        warnings.append(
            "Transport suggestions are approximate and require manual confirmation before saving."
        )
        return {
            "generated_at": now_iso(),
            "privacy_notice": (
                "No account, token, customer name or address is sent automatically. "
                "Allowlisted search links disclose route coordinates only after the user opens them."
            ),
            "warnings": warnings,
            "suggestions": suggestions,
        }

    def archive_trip_stop(
        self,
        plan_id: str,
        stop_id: str,
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> Optional[dict]:
        """Archive a stop from a trip plan."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        current = self.core._get_trip_stop(stop_id)
        if not current or current["plan_id"] != plan_id:
            return None
        self.core._assert_row_version(current, row_version)
        conn = self.core.lead_repo.conn
        now = now_iso()
        params = [now, now, actor_id, stop_id, plan_id]
        where = "id = ? AND plan_id = ? AND archived_at IS NULL"
        if row_version is not None:
            where += " AND row_version = ?"
            params.append(row_version)
        try:
            cursor = conn.execute(
                f"""
                UPDATE trip_plan_stops
                SET archived_at = ?, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE {where}
                """,
                tuple(params),
            )
            if cursor.rowcount == 0:
                latest = self.core._get_trip_stop(stop_id)
                if latest:
                    self.core._assert_row_version(latest, row_version)
                conn.rollback()
                return None
            self.free_stop_repo.normalize_sequences(plan_id, actor_id, now)
            self._invalidate_trip_itinerary(plan_id, actor_id, "stop_removed", now)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def archive_trip_free_stop(
        self,
        plan_id: str,
        free_stop_id: str,
        actor_id: str,
        actor_role: str,
        row_version: Optional[int] = None,
    ) -> Optional[dict]:
        """Archive an independent route stop without Lead-side effects."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        current = self.free_stop_repo.get_active(free_stop_id)
        if not current or current["plan_id"] != plan_id:
            return None
        self.core._assert_row_version(current, row_version)
        conn = self.core.lead_repo.conn
        now = now_iso()
        params = [now, now, actor_id, free_stop_id, plan_id]
        where = "id = ? AND plan_id = ? AND archived_at IS NULL"
        if row_version is not None:
            where += " AND row_version = ?"
            params.append(row_version)
        try:
            cursor = conn.execute(
                f"""
                UPDATE trip_plan_free_stops
                SET archived_at = ?, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE {where}
                """,
                tuple(params),
            )
            if cursor.rowcount == 0:
                latest = self.free_stop_repo.get_active(free_stop_id)
                if latest:
                    self.core._assert_row_version(latest, row_version)
                conn.rollback()
                return None
            self.free_stop_repo.normalize_sequences(plan_id, actor_id, now)
            self._invalidate_trip_itinerary(plan_id, actor_id, "stop_removed", now)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def export_trip_plan_markdown(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[str]:
        """Export a trip plan as Markdown."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        self._assert_itinerary_exportable(plan)
        lines = [
            f"# {plan['title']}",
            "",
            f"- Status: {plan.get('status') or 'Draft'}",
            f"- Date: {plan.get('start_date') or '-'} to {plan.get('end_date') or '-'}",
            f"- Region: {plan.get('region') or '-'}",
            f"- Owner: {plan.get('owner_name') or '-'}",
            f"- Origin: {plan.get('origin_name') or '-'}",
            f"- Destination: {plan.get('destination_name') or '-'}",
            # The shared travel windows describe the whole team leaving at once,
            # which a team trip does not do: each member's own dates are in the
            # travel team table below instead.
            *([] if team_export.is_team(plan) else [
                f"- Departure Window: {plan.get('departure_window_start') or '-'} to {plan.get('departure_window_end') or '-'}",
                f"- Return Window: {plan.get('return_window_start') or '-'} to {plan.get('return_window_end') or '-'}",
            ]),
            f"- Travel Mode: {plan.get('travel_mode') or 'auto'}",
            f"- Planning Notes: {plan.get('description') or '-'}",
            "",
            "## Customer Visit Schedule",
            "",
            "| " + " | ".join(
                self._visit_export_headers(team_export.is_team(plan))
            ) + " |",
            _md_separator(self._visit_export_headers(team_export.is_team(plan)),
                          right_align={"No."}),
        ]
        summary = plan.get("itinerary_summary") or {}
        team = team_export.is_team(plan)
        if summary and team:
            # Named as an aggregate: two colleagues on one flight count it
            # twice, which is right for how much travelling was done and wrong
            # for how long the route is.
            lines[7:7] = [
                f"- Team Aggregate Travel Distance: "
                f"{summary.get('total_distance_km') or '-'} km",
                f"- Team Aggregate Travel Hours: "
                f"{summary.get('total_travel_hours') or '-'}",
                f"- Route Complete: "
                f"{'yes' if summary.get('route_complete') else 'no'}",
            ]
        elif summary:
            lines[7:7] = [
                f"- Calculated End: {summary.get('calculated_end_date') or '-'}",
                f"- Business Days: {summary.get('total_business_days') or '-'}",
                f"- Travel Distance: {summary.get('total_distance_km') or '-'} km",
                f"- Travel Hours: {summary.get('total_travel_hours') or '-'}",
            ]

        if team:
            # The team block is written before the visits, after the plan's own
            # details, so the bullets above stay one list.
            head = lines[:lines.index("## Customer Visit Schedule")]
            rest = lines[lines.index("## Customer Visit Schedule"):]
            lines = head + team_export.header_lines(plan) \
                + team_export.risk_lines(plan) + [""] + rest
        customer_stops = [
            stop for stop in plan.get("stops", [])
            if stop.get("stop_kind") != "free"
        ]
        for number, stop in enumerate(customer_stops, start=1):
            row = (
                self._team_visit_row(plan, stop, number) if team
                else self._visit_export_row(stop, number)
            )
            lines.append(
                "| " + " | ".join(
                    self.core._md_cell(row[header])
                    for header in self._visit_export_headers(team)
                ) + " |"
            )
        free_stops = [
            stop for stop in plan.get("stops", [])
            if stop.get("stop_kind") == "free"
        ]
        if free_stops:
            headers = [
                "#", "Place", "Category", "Date / Period", "Duration",
                *(["Attendees"] if team else []), "Purpose", "Notes",
            ]
            lines.extend([
                "", "## Non-customer Schedule", "",
                "| " + " | ".join(headers) + " |",
                _md_separator(headers, right_align={"#", "Duration"}),
            ])
            for stop in free_stops:
                date_text = " ".join(
                    str(value) for value in (
                        stop.get("planned_date"), stop.get("planned_start_period")
                    ) if value
                )
                cells = [
                    stop.get("sequence_no") or "",
                    self.core._md_cell(stop.get("location_name")),
                    self.core._md_cell(stop.get("category")),
                    self.core._md_cell(date_text),
                    (stop.get("duration_half_days") or 2) / 2,
                    *([self.core._md_cell(
                        team_export.attendee_names(plan, stop)
                    )] if team else []),
                    self.core._md_cell(stop.get("visit_purpose")),
                    self.core._md_cell(stop.get("notes")),
                ]
                lines.append(
                    "| " + " | ".join(str(cell) for cell in cells) + " |"
                )
        lines.extend(
            [
                "",
                "## Route Legs",
                "",
                "|" + (" Member |" if team else "")
                + " # | From | To | Mode | Distance km | Time hours | Start | End | Travel half-days | Travel days | Planning basis | Notes |",
                "|" + ("---|" if team else "")
                + "---|---|---|---|---:|---:|---|---|---:|---:|---|---|",
            ]
        )
        legs = plan.get("legs") or []
        if not legs:
            lines.append(
                ("| - " if team else "")
                + "| - | - | - | - | - | - | - | - | - | - | No saved route legs | - |"
            )
        for leg in legs:
            lines.append(
                (f"| {team_export.member_name(plan, leg.get('member_id')) or '-'} "
                 if team else "")
                + "| {seq} | {from_label} | {to_label} | {mode} | {distance} | {hours} | {start} | {end} | {half_days} | {days} | {basis} | {notes} |".format(
                    seq=leg.get("sequence_no") or "",
                    from_label=self.core._md_cell(leg.get("from_label") or leg.get("from")),
                    to_label=self.core._md_cell(leg.get("to_label") or leg.get("to")),
                    mode=self.core._md_cell(leg.get("selected_mode") or leg.get("mode")),
                    distance=self.core._md_cell(leg.get("distance_km")),
                    hours=self.core._md_cell(leg.get("time_hours")),
                    start=self.core._md_cell(" ".join(
                        str(value) for value in (
                            leg.get("planned_start_date"),
                            leg.get("planned_start_period"),
                        ) if value
                    )),
                    end=self.core._md_cell(" ".join(
                        str(value) for value in (
                            leg.get("planned_end_date"), leg.get("planned_end_period"),
                        ) if value
                    )),
                    half_days=self.core._md_cell(leg.get("travel_half_days")),
                    days=self.core._md_cell((leg.get("travel_half_days") or 0) / 2),
                    basis=self.core._md_cell(self._trip_leg_confirmation(leg)),
                    notes=self.core._md_cell(leg.get("notes")),
                )
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _visit_export_headers(team: bool = False) -> list[str]:
        # Two extra columns in team planning: a visit exported without who went
        # and how its time was decided cannot be read back.
        return [
            *(["Attendees", "Schedule State"] if team else []),
            "No.",
            "Company Name",
            "Full Address",
            "Recommended Visit Date",
            "Demo Laser",
            "PO Laser",
            "Other Equipment",
            CUSTOMER_PERSONNEL_HEADER,
            CHANNEL_PARTNER_COMPANIONS_HEADER,
            "Visiting topic",
        ]

    def _team_visit_row(self, plan: dict, stop: dict, number: int) -> dict:
        return {
            **self._visit_export_row(stop, number),
            "Attendees": team_export.attendee_names(plan, stop),
            "Schedule State": team_export.schedule_state(stop),
        }

    def _visit_export_row(self, stop: dict, number: int) -> dict:
        return formal_visit_row(stop, number)

    def get_trip_execution(
        self,
        plan_id: str,
        actor_id: str,
        actor_role: str,
        visit_date: Optional[str] = None,
    ) -> Optional[dict]:
        """Return day-oriented visit execution data for a trip plan."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        self._assert_itinerary_exportable(plan)

        all_schedule_items = list(plan.get("schedule_items") or [])
        days = sorted(
            {item.get("date") for item in all_schedule_items if item.get("date")}
        ) or self._planned_days(plan.get("stops") or [])
        selected_date = visit_date or (days[0] if days else None)
        stops = [
            stop for stop in plan.get("stops", [])
            if not selected_date or self._stop_in_day(stop, selected_date)
        ]
        return {
            "plan": {key: value for key, value in plan.items() if key != "stops"},
            "days": days,
            "selected_date": selected_date,
            "stops": stops,
            "schedule_items": [
                item for item in all_schedule_items
                if not selected_date or item.get("date") == selected_date
            ],
        }

    def export_trip_execution_markdown(
        self,
        plan_id: str,
        actor_id: str,
        actor_role: str,
        visit_date: Optional[str] = None,
    ) -> Optional[str]:
        """Export a day itinerary and visit report as Markdown."""
        execution = self.get_trip_execution(plan_id, actor_id, actor_role, visit_date)
        if execution is None:
            return None
        plan = execution["plan"]
        selected_date = execution.get("selected_date") or "All scheduled days"
        lines = [
            f"# {plan.get('title') or 'Trip Plan'} - Visit Execution",
            "",
            f"- Date: {selected_date}",
            f"- Owner: {plan.get('owner_name') or '-'}",
            f"- Region: {plan.get('region') or '-'}",
            "",
            "## Daily Timeline",
            "",
            "|" + (" Member |" if team_export.is_team(plan) else "")
            + " Order | Date | Period | Type | Item | Mode | Distance km | Time hours |",
            "|" + ("---|" if team_export.is_team(plan) else "")
            + "---:|---|---|---|---|---|---:|---:|",
        ]
        for item in execution.get("schedule_items", []):
            lines.append(
                (f"| {team_export.member_name(plan, item.get('member_id')) or '-'} "
                 if team_export.is_team(plan) else "")
                + "| {order} | {date} | {period} | {kind} | {title} | {mode} | {distance} | {hours} |".format(
                    order=item.get("schedule_index") or "",
                    date=self.core._md_cell(item.get("date")),
                    period=self.core._md_cell(item.get("period")),
                    kind=self.core._md_cell(item.get("item_type")),
                    title=self.core._md_cell(item.get("title")),
                    mode=self.core._md_cell(item.get("selected_mode")),
                    distance=self.core._md_cell(item.get("distance_km")),
                    hours=self.core._md_cell(item.get("time_hours")),
                )
            )
        lines.extend([
            "",
            "## Daily Itinerary",
            "",
            "| # | Date / Period | Type | Category | Place / Customer | Contact | Address | Lead | Purpose | Result |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ])
        for stop in execution.get("stops", []):
            briefing = stop.get("briefing") or {}
            briefing_contacts = briefing.get("contacts") or []
            contact = "\n".join(
                " / ".join(
                    str(value) for value in (
                        item.get("name"), item.get("position"), item.get("role"),
                        item.get("phone"), item.get("email"), item.get("notes"),
                    ) if value
                )
                for item in briefing_contacts
                if any(item.get(key) for key in ("name", "email", "phone"))
            )
            if not contact:
                contact = " / ".join(
                    x for x in (
                        stop.get("contact_name"),
                        stop.get("contact_phone") or stop.get("contact_email"),
                    ) if x
                )
            location = stop.get("visit_location") or {}
            address = location.get("full_address") or ", ".join(
                x for x in (
                    stop.get("address"), stop.get("city"),
                    stop.get("postal_code"), stop.get("country"),
                ) if x
            )
            start = " ".join(
                str(value) for value in (
                    stop.get("planned_date"), stop.get("planned_start_period")
                ) if value
            )
            end = " ".join(
                str(value) for value in (
                    stop.get("planned_end_date"), stop.get("planned_end_period")
                ) if value
            )
            dates = start if not end or end == start else f"{start} to {end}"
            lines.append(
                "| {seq} | {dates} | {kind} | {category} | {customer} | {contact} | {address} | {lead} | {purpose} | {result} |".format(
                    seq=stop.get("sequence_no") or "",
                    dates=self.core._md_cell(dates),
                    kind=self.core._md_cell(stop.get("stop_kind") or "customer"),
                    category=self.core._md_cell(stop.get("category")),
                    customer=self.core._md_cell(
                        location.get("label") or stop.get("location_name")
                        or stop.get("customer_name")
                    ),
                    contact=self.core._md_cell(contact),
                    address=self.core._md_cell(address),
                    lead=self.core._md_cell(stop.get("lead_display_id") or stop.get("lead_title")),
                    purpose=self.core._md_cell(stop.get("visit_purpose")),
                    result=self.core._md_cell(stop.get("result_status")),
                )
            )

        lines.extend(["", "## Visit Reports", ""])
        for stop in execution.get("stops", []):
            if stop.get("stop_kind") == "free":
                continue
            lines.extend(
                [
                    f"### {stop.get('sequence_no') or ''}. {stop.get('customer_name') or '-'}",
                    "",
                    f"- Lead: {stop.get('lead_display_id') or '-'} {stop.get('lead_title') or ''}".rstrip(),
                    f"- Needs: {stop.get('visit_customer_needs') or '-'}",
                    f"- Competitor: {stop.get('visit_competitor') or '-'}",
                    f"- Budget: {stop.get('visit_budget') or '-'}",
                    f"- Decision Maker: {stop.get('visit_decision_maker') or '-'}",
                    f"- Next Action: {stop.get('visit_next_action') or '-'}",
                    f"- Actually visited: "
                    f"{' '.join(str(value) for value in (stop.get('actual_visit_date'), stop.get('actual_visit_period')) if value) or '-'}",
                    f"- Sample Needed: {_answer_text(stop.get('visit_sample_needed'))}",
                    f"- Quote Needed: {_answer_text(stop.get('visit_quote_needed'))}",
                    f"- Notes: {stop.get('result_notes') or stop.get('notes') or '-'}",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"

    def _planned_days(self, stops: list[dict]) -> list[str]:
        days = set()
        for stop in stops:
            start = self.core._parse_date(stop.get("planned_date"))
            end = self.core._parse_date(stop.get("planned_end_date")) or start
            if not start:
                continue
            cursor = start
            while cursor <= end:
                days.add(cursor.isoformat())
                cursor += timedelta(days=1)
        return sorted(days)

    def _stop_in_day(self, stop: dict, value: str) -> bool:
        target = self.core._parse_date(value)
        start = self.core._parse_date(stop.get("planned_date"))
        end = self.core._parse_date(stop.get("planned_end_date")) or start
        if not target or not start:
            return False
        return start <= target <= end

    def export_trip_plan_csv(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[str]:
        """Export a trip plan as CSV."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        self._assert_itinerary_exportable(plan)
        output = io.StringIO()
        stop_headers = [
            "sequence", "stop_kind", "category", "location_name", "customer",
            "address", "city", "postal_code", "country", "visit_location_lat",
            "visit_location_lng", "visit_location_source", "lead_display_id",
            "lead_title", "stage", "owner", "value", "planned_date",
            "planned_start_period", "planned_end_date", "planned_end_period",
            "duration_half_days", "stay_days", "preferred_period",
            "schedule_locked", "confirmation_status", "travel_from",
            "travel_mode", "travel_distance_km", "travel_time_hours",
            "travel_days", "purpose", "result_status", "result_notes",
            "customer_needs", "competitor", "budget", "decision_maker",
            "next_action", "sample_needed", "quote_needed",
            "actual_visit_date", "actual_visit_period", "notes",
        ]
        # In team planning a stop without who attended it and how its time was
        # decided is not a usable record.
        team = team_export.is_team(plan)
        if team:
            stop_headers += [
                "attendee_user_ids", "attendee_names", "schedule_state",
            ]
        leg_headers = [
            "leg_sequence", "leg_key", "leg_from", "leg_to", "leg_mode",
            "leg_distance_km", "leg_time_hours", "leg_travel_half_days",
            "leg_travel_days", "leg_planned_start_date",
            "leg_planned_start_period", "leg_planned_end_date",
            "leg_planned_end_period", "leg_notes", "leg_confirmation",
        ]
        if team:
            leg_headers = ["leg_member_id", "leg_member_name", *leg_headers]
        plan_headers = [
            "plan_title", "plan_description", "plan_start_date", "plan_end_date",
            "plan_origin", "plan_destination", "departure_window_start",
            "departure_window_end", "return_window_start", "return_window_end",
        ]
        headers = [
            "record_type", *self._visit_export_headers(), *stop_headers,
            *leg_headers, *plan_headers,
        ]
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        plan_cells = {
            "plan_title": plan.get("title"),
            "plan_description": plan.get("description"),
            "plan_start_date": plan.get("start_date"),
            "plan_end_date": plan.get("end_date"),
            "plan_origin": plan.get("origin_name"),
            "plan_destination": plan.get("destination_name"),
            # Blank on a team trip: the shared windows describe the whole team
            # leaving at once, which it does not do. Each member's own dates are
            # in the member columns. The columns stay so the file shape does not
            # change between one kind of plan and the other.
            **{
                field: None if team_export.is_team(plan) else plan.get(field)
                for field in (
                    "departure_window_start", "departure_window_end",
                    "return_window_start", "return_window_end",
                )
            },
        }

        def write_row(row: dict) -> None:
            writer.writerow(
                {key: self.core._csv_cell(row.get(key)) for key in headers}
            )

        customer_number = 0
        for stop in plan.get("stops", []):
            is_customer = stop.get("stop_kind") != "free"
            if is_customer:
                customer_number += 1
                example = self._visit_export_row(stop, customer_number)
            else:
                example = {key: "" for key in self._visit_export_headers()}
            location = stop.get("visit_location") or {}
            attendees = (
                {
                    "attendee_user_ids": " ".join(
                        team_export.attendee_ids(stop)
                    ),
                    "attendee_names": team_export.attendee_names(plan, stop),
                    "schedule_state": team_export.schedule_state(stop),
                } if team else {}
            )
            write_row(
                {
                    "record_type": "customer_stop" if is_customer else "free_stop",
                    **example,
                    **attendees,
                    "sequence": stop.get("sequence_no"),
                    "stop_kind": stop.get("stop_kind") or "customer",
                    "category": stop.get("category"),
                    "location_name": (
                        location.get("label") or stop.get("location_name")
                        or stop.get("customer_name")
                    ),
                    "customer": stop.get("customer_name") if is_customer else None,
                    "address": location.get("address", stop.get("address")),
                    "city": location.get("city", stop.get("city")),
                    "postal_code": location.get("postal_code", stop.get("postal_code")),
                    "country": location.get("country", stop.get("country")),
                    "visit_location_lat": location.get("lat", stop.get("lat")),
                    "visit_location_lng": location.get("lng", stop.get("lng")),
                    "visit_location_source": location.get("source"),
                    "lead_display_id": stop.get("lead_display_id"),
                    "lead_title": stop.get("lead_title"),
                    "stage": stop.get("sales_stage"),
                    "owner": stop.get("lead_owner_name"),
                    "value": self.core._num(stop.get("deal_amount"))
                    or self.core._num(stop.get("estimated_value")),
                    "planned_date": stop.get("planned_date"),
                    "planned_start_period": stop.get("planned_start_period"),
                    "planned_end_date": stop.get("planned_end_date"),
                    "planned_end_period": stop.get("planned_end_period"),
                    "duration_half_days": stop.get("duration_half_days"),
                    "stay_days": stop.get("stay_days"),
                    "preferred_period": stop.get("preferred_period"),
                    "schedule_locked": "Yes" if stop.get("schedule_locked") else "No",
                    "confirmation_status": stop.get("confirmation_status"),
                    "travel_from": stop.get("travel_from_label"),
                    "travel_mode": stop.get("travel_mode"),
                    "travel_distance_km": stop.get("travel_distance_km"),
                    "travel_time_hours": stop.get("travel_time_hours"),
                    "travel_days": stop.get("travel_days"),
                    "purpose": stop.get("visit_purpose"),
                    "result_status": stop.get("result_status"),
                    "result_notes": stop.get("result_notes"),
                    "customer_needs": stop.get("visit_customer_needs"),
                    "competitor": stop.get("visit_competitor"),
                    "budget": stop.get("visit_budget"),
                    "decision_maker": stop.get("visit_decision_maker"),
                    "next_action": stop.get("visit_next_action"),
                    "sample_needed": _answer_text(stop.get("visit_sample_needed")),
                    "quote_needed": _answer_text(stop.get("visit_quote_needed")),
                    "actual_visit_date": stop.get("actual_visit_date"),
                    "actual_visit_period": stop.get("actual_visit_period"),
                    "notes": stop.get("notes"),
                    **plan_cells,
                }
            )
        for leg in plan.get("legs") or []:
            write_row(
                {
                    "record_type": "leg",
                    **({
                        "leg_member_id": leg.get("member_id"),
                        "leg_member_name": team_export.member_name(
                            plan, leg.get("member_id")
                        ),
                    } if team else {}),
                    "leg_sequence": leg.get("sequence_no"),
                    "leg_key": leg.get("leg_key"),
                    "leg_from": leg.get("from_label") or leg.get("from"),
                    "leg_to": leg.get("to_label") or leg.get("to"),
                    "leg_mode": leg.get("selected_mode") or leg.get("mode"),
                    "leg_distance_km": leg.get("distance_km"),
                    "leg_time_hours": leg.get("time_hours"),
                    "leg_travel_half_days": leg.get("travel_half_days"),
                    "leg_travel_days": (leg.get("travel_half_days") or 0) / 2,
                    "leg_planned_start_date": leg.get("planned_start_date"),
                    "leg_planned_start_period": leg.get("planned_start_period"),
                    "leg_planned_end_date": leg.get("planned_end_date"),
                    "leg_planned_end_period": leg.get("planned_end_period"),
                    "leg_notes": leg.get("notes"),
                    "leg_confirmation": self._trip_leg_confirmation(leg),
                    **plan_cells,
                }
            )
        return output.getvalue()

    def _formal_trip_export(self, plan_id: str, actor_id: str, actor_role: str,
                            variant: str = FULL_VARIANT):
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None, None
        self._assert_itinerary_exportable(plan)
        model = build_trip_export_model(
            plan, self._trip_leg_confirmation, variant
        )
        return plan, model

    def export_trip_plan_xlsx(self, plan_id: str, actor_id: str, actor_role: str,
                              variant: str = FULL_VARIANT) -> Optional[bytes]:
        """Export a trip plan as a styled Excel workbook."""
        _, model = self._formal_trip_export(plan_id, actor_id, actor_role, variant)
        return None if model is None else render_trip_xlsx(model)

    def export_trip_plan_html(self, plan_id: str, actor_id: str, actor_role: str,
                              variant: str = FULL_VARIANT) -> Optional[bytes]:
        """Export a trip plan as a self-contained printable page."""
        _, model = self._formal_trip_export(plan_id, actor_id, actor_role, variant)
        return None if model is None else render_trip_html(model)

    def export_trip_working_xlsx(
        self, plan_id: str, actor_id: str, actor_role: str
    ) -> Optional[bytes]:
        """The workbook the field team fills in and sends back.

        It is built from the same saved plan as the other files, but it is a
        contract rather than a view: the guards that stop an out-of-date route
        being published apply here too, because a result reported against a
        route nobody saved cannot be matched back to it.
        """
        plan, _ = self._formal_trip_export(
            plan_id, actor_id, actor_role, SHARED_VARIANT
        )
        if plan is None:
            return None
        workbook_id = generate_uuid()
        model = build_working_model(plan, now_iso(), workbook_id)
        self._record_working_export(model, actor_id)
        return render_working_xlsx(model)

    def _record_working_export(self, model: dict, actor_id: str) -> None:
        """Keep what this workbook was issued with, where the file cannot reach.

        Issuing a workbook is a promise about what comes back, so the promise
        is written down here rather than inside the file: a returned workbook
        is matched against this, and nothing it says about which visit a row is
        or what the row held is believed.
        """
        conn = self.core.lead_repo.conn
        stamp = now_iso()
        conn.execute(
            "INSERT INTO trip_working_exports "
            "(workbook_id, plan_id, format, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (model["workbook_id"], model["plan_id"], model["format"], stamp, actor_id),
        )
        conn.executemany(
            "INSERT INTO trip_working_export_rows "
            "(workbook_id, row_token, stop_id, row_version, baseline_json) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (model["workbook_id"], row["row_token"], row["stop_id"],
                 row["row_version"], json.dumps(row["baseline"], ensure_ascii=False))
                for row in model["manifest"]
            ],
        )
        conn.commit()

    def export_trip_plan_ics(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[bytes]:
        """Export half-day itinerary slots as all-day calendar events.

        A calendar is imported and forwarded on its own, so it carries the
        shared arrangement: where everyone is, when, and how they travel.
        """
        plan, model = self._formal_trip_export(
            plan_id, actor_id, actor_role, SHARED_VARIANT
        )
        if model is None:
            return None
        return render_trip_ics(model)
