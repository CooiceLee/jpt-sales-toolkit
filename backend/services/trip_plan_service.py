from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Optional

from ..repositories.base import generate_uuid, now_iso

class TripPlanService:
    """Extracted ReviewService component."""

    def __init__(self, core):
        self.core = core

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
                   COUNT(s.id) AS stop_count
            FROM trip_plans p
            LEFT JOIN users u ON p.owner_id = u.id
            LEFT JOIN trip_plan_stops s
                ON p.id = s.plan_id AND s.archived_at IS NULL
            WHERE p.archived_at IS NULL
        """
        params: list = []
        if actor_role != "leader":
            sql += " AND p.owner_id = ?"
            params.append(actor_id)
        sql += " GROUP BY p.id ORDER BY p.updated_at DESC"
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
                destination_lat, destination_lng, travel_mode, avoid_weekends,
                holiday_dates, description, status, created_at, created_by,
                updated_at, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                prepared.get("avoid_weekends", 1),
                prepared.get("holiday_dates"),
                prepared.get("description"),
                data.get("status") or "Draft",
                now,
                actor_id,
                now,
                actor_id,
            ),
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
                   c.address, c.region, c.lat, c.lng, c.geocode_source,
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
        plan_data["stops"] = [dict(row) for row in stops]
        return plan_data

    def update_trip_plan(self, plan_id: str, data: dict, actor_id: str, actor_role: str) -> Optional[dict]:
        """Update trip plan header fields."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        expected_version = data.pop("row_version", None)
        self.core._assert_row_version(plan, expected_version)

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
            "avoid_weekends",
            "holiday_dates",
        }
        update_data = self.core._prepare_trip_plan_data({key: value for key, value in data.items() if key in allowed})
        if not update_data:
            return plan

        if actor_role != "leader":
            update_data.pop("owner_id", None)

        update_data["updated_at"] = now_iso()
        update_data["updated_by"] = actor_id
        update_data["row_version"] = int(plan.get("row_version") or 1) + 1
        assignments = ", ".join(f"{key} = ?" for key in update_data)
        params = [*update_data.values(), plan_id]
        where = "id = ?"
        if expected_version is not None:
            where += " AND row_version = ?"
            params.append(expected_version)
        cursor = self.core.lead_repo.conn.execute(
            f"UPDATE trip_plans SET {assignments} WHERE {where}",
            tuple(params),
        )
        if cursor.rowcount == 0:
            current = self.core.get_trip_plan(plan_id, actor_id, actor_role)
            if current:
                self.core._assert_row_version(current, expected_version)
        self.core.lead_repo.conn.commit()
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

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
        next_sequence = conn.execute(
            """
            SELECT COALESCE(MAX(sequence_no), 0) + 1
            FROM trip_plan_stops
            WHERE plan_id = ? AND archived_at IS NULL
            """,
            (plan_id,),
        ).fetchone()[0]
        now = now_iso()
        stop_id = generate_uuid()
        conn.execute(
            """
            INSERT INTO trip_plan_stops (
                id, plan_id, customer_id, lead_id, sequence_no, planned_date,
                planned_end_date, stay_days, visit_purpose, notes, result_status,
                created_at, created_by, updated_at, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Planned', ?, ?, ?, ?)
            """,
            (
                stop_id,
                plan_id,
                customer_id,
                lead_id,
                data.get("sequence_no") or next_sequence,
                data.get("planned_date"),
                data.get("planned_end_date"),
                self.core._clean_stay_days(data.get("stay_days")),
                data.get("visit_purpose"),
                data.get("notes"),
                now,
                actor_id,
                now,
                actor_id,
            ),
        )
        conn.execute(
            """
            UPDATE trip_plans
            SET updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ?
            """,
            (now, actor_id, plan_id),
        )
        conn.commit()
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

        allowed = {
            "sequence_no",
            "planned_date",
            "planned_end_date",
            "stay_days",
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
            "lead_id",
        }
        update_data = {key: value for key, value in data.items() if key in allowed}
        if "stay_days" in update_data:
            update_data["stay_days"] = self.core._clean_stay_days(update_data["stay_days"])
        for bool_key in ("visit_sample_needed", "visit_quote_needed"):
            if bool_key in update_data:
                update_data[bool_key] = 1 if update_data[bool_key] else 0
        if "lead_id" in update_data and update_data["lead_id"]:
            lead = self.core._visible_lead_by_id(update_data["lead_id"], actor_id, actor_role)
            if not lead or lead["customer_id"] != current["customer_id"]:
                raise ValueError("Lead is not visible or does not belong to this customer")

        should_sync_activity = (
            data.get("result_status") in {"Visited", "Follow-up Needed", "Skipped"}
            or data.get("result_notes")
            or any(key in data for key in (
                "visit_customer_needs",
                "visit_competitor",
                "visit_budget",
                "visit_decision_maker",
                "visit_next_action",
                "visit_sample_needed",
                "visit_quote_needed",
            ))
        )
        if update_data or should_sync_activity:
            conn = self.core.lead_repo.conn
            try:
                if update_data:
                    update_data["updated_at"] = now_iso()
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
                    conn.execute(
                        """
                        UPDATE trip_plans
                        SET updated_at = ?, updated_by = ?, row_version = row_version + 1
                        WHERE id = ?
                        """,
                        (now_iso(), actor_id, plan_id),
                    )

                updated_stop = self.core._get_trip_stop(stop_id)
                if updated_stop and should_sync_activity:
                    self.core._sync_trip_result_activity(updated_stop, actor_id)
                    self.core._sync_trip_followup_activity(updated_stop, actor_id)
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
            for sequence_no, stop_id in enumerate(stop_ids, start=1):
                conn.execute(
                    """
                    UPDATE trip_plan_stops
                    SET sequence_no = ?, updated_at = ?, updated_by = ?,
                        row_version = row_version + 1
                    WHERE id = ? AND plan_id = ? AND archived_at IS NULL
                    """,
                    (sequence_no, now, actor_id, stop_id, plan_id),
                )
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
        calculation = self.core._calculate_trip_itinerary(plan, data)
        stop_updates = calculation["stop_updates"]
        plan_updates = calculation["plan_updates"]

        conn = self.core.lead_repo.conn
        now = now_iso()
        try:
            for item in stop_updates:
                conn.execute(
                    """
                    UPDATE trip_plan_stops
                    SET sequence_no = ?, planned_date = ?, planned_end_date = ?,
                        stay_days = ?, travel_from_label = ?, travel_mode = ?,
                        travel_distance_km = ?, travel_time_hours = ?, travel_days = ?,
                        updated_at = ?, updated_by = ?, row_version = row_version + 1
                    WHERE id = ? AND plan_id = ? AND archived_at IS NULL
                    """,
                    (
                        item["sequence_no"],
                        item["planned_date"],
                        item["planned_end_date"],
                        item["stay_days"],
                        item["travel_from_label"],
                        item["travel_mode"],
                        item["travel_distance_km"],
                        item["travel_time_hours"],
                        item["travel_days"],
                        now,
                        actor_id,
                        item["id"],
                        plan_id,
                    ),
                )

            plan_updates["updated_at"] = now
            plan_updates["updated_by"] = actor_id
            plan_updates["row_version"] = int(plan.get("row_version") or 1) + 1
            assignments = ", ".join(f"{key} = ?" for key in plan_updates)
            params = [*plan_updates.values(), plan_id]
            where = "id = ?"
            if expected_version is not None:
                where += " AND row_version = ?"
                params.append(expected_version)
            cursor = conn.execute(
                f"UPDATE trip_plans SET {assignments} WHERE {where}",
                tuple(params),
            )
            if cursor.rowcount == 0:
                latest = self.core.get_trip_plan(plan_id, actor_id, actor_role)
                if latest:
                    self.core._assert_row_version(latest, expected_version)
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
        calculation = self.core._calculate_trip_itinerary(plan, data)
        return self.core._trip_itinerary_preview_plan(plan, calculation)

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
        cursor = self.core.lead_repo.conn.execute(
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
        self.core._normalize_trip_stop_sequences(plan_id, actor_id, now)
        conn.execute(
            """
            UPDATE trip_plans
            SET updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ?
            """,
            (now, actor_id, plan_id),
        )
        conn.commit()
        return self.core.get_trip_plan(plan_id, actor_id, actor_role)

    def export_trip_plan_markdown(self, plan_id: str, actor_id: str, actor_role: str) -> Optional[str]:
        """Export a trip plan as Markdown."""
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            return None
        lines = [
            f"# {plan['title']}",
            "",
            f"- Status: {plan.get('status') or 'Draft'}",
            f"- Date: {plan.get('start_date') or '-'} to {plan.get('end_date') or '-'}",
            f"- Region: {plan.get('region') or '-'}",
            f"- Owner: {plan.get('owner_name') or '-'}",
            f"- Origin: {plan.get('origin_name') or '-'}",
            f"- Destination: {plan.get('destination_name') or '-'}",
            f"- Travel Mode: {plan.get('travel_mode') or 'auto'}",
            "",
            "## Stops",
            "",
            "| # | Customer | Location | Lead | Stage | Value | Dates | Stay | Travel From | Purpose | Result | Notes |",
            "|---|---|---|---|---|---:|---|---:|---|---|---|---|",
        ]
        summary = plan.get("itinerary_summary") or {}
        if summary:
            lines[7:7] = [
                f"- Calculated End: {summary.get('calculated_end_date') or '-'}",
                f"- Business Days: {summary.get('total_business_days') or '-'}",
                f"- Travel Distance: {summary.get('total_distance_km') or '-'} km",
                f"- Travel Hours: {summary.get('total_travel_hours') or '-'}",
            ]
        for stop in plan.get("stops", []):
            value = self.core._num(stop.get("deal_amount")) or self.core._num(stop.get("estimated_value"))
            dates = " to ".join(x for x in [stop.get("planned_date"), stop.get("planned_end_date")] if x)
            travel_from = stop.get("travel_from_label") or "-"
            if stop.get("travel_distance_km"):
                travel_from = f"{travel_from} ({stop.get('travel_mode') or '-'}, {stop.get('travel_distance_km')} km)"
            lines.append(
                "| {seq} | {customer} | {location} | {lead} | {stage} | {value} | {dates} | {stay} | {travel_from} | {purpose} | {result} | {notes} |".format(
                    seq=stop.get("sequence_no") or "",
                    customer=self.core._md_cell(stop.get("customer_name")),
                    location=self.core._md_cell(", ".join(x for x in [stop.get("city"), stop.get("country")] if x)),
                    lead=self.core._md_cell(stop.get("lead_display_id")),
                    stage=self.core._md_cell(stop.get("sales_stage")),
                    value=f"{value:,.0f}" if value else "-",
                    dates=self.core._md_cell(dates),
                    stay=stop.get("stay_days") or 1,
                    travel_from=self.core._md_cell(travel_from),
                    purpose=self.core._md_cell(stop.get("visit_purpose")),
                    result=self.core._md_cell(stop.get("result_status")),
                    notes=self.core._md_cell(stop.get("result_notes") or stop.get("notes")),
                )
            )
        return "\n".join(lines) + "\n"

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

        days = self._planned_days(plan.get("stops") or [])
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
            "## Daily Itinerary",
            "",
            "| # | Date | Customer | Contact | Address | Lead | Purpose | Result |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for stop in execution.get("stops", []):
            contact = " / ".join(x for x in [stop.get("contact_name"), stop.get("contact_phone") or stop.get("contact_email")] if x)
            address = ", ".join(x for x in [stop.get("address"), stop.get("city"), stop.get("country")] if x)
            dates = " to ".join(x for x in [stop.get("planned_date"), stop.get("planned_end_date")] if x)
            lines.append(
                "| {seq} | {dates} | {customer} | {contact} | {address} | {lead} | {purpose} | {result} |".format(
                    seq=stop.get("sequence_no") or "",
                    dates=self.core._md_cell(dates),
                    customer=self.core._md_cell(stop.get("customer_name")),
                    contact=self.core._md_cell(contact),
                    address=self.core._md_cell(address),
                    lead=self.core._md_cell(stop.get("lead_display_id") or stop.get("lead_title")),
                    purpose=self.core._md_cell(stop.get("visit_purpose")),
                    result=self.core._md_cell(stop.get("result_status")),
                )
            )

        lines.extend(["", "## Visit Reports", ""])
        for stop in execution.get("stops", []):
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
                    f"- Sample Needed: {'Yes' if stop.get('visit_sample_needed') else 'No'}",
                    f"- Quote Needed: {'Yes' if stop.get('visit_quote_needed') else 'No'}",
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
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "sequence",
            "customer",
            "city",
            "country",
            "lead_display_id",
            "lead_title",
            "stage",
            "owner",
            "value",
            "planned_date",
            "planned_end_date",
            "stay_days",
            "travel_from",
            "travel_mode",
            "travel_distance_km",
            "travel_time_hours",
            "travel_days",
            "purpose",
            "result_status",
            "result_notes",
            "customer_needs",
            "competitor",
            "budget",
            "decision_maker",
            "next_action",
            "sample_needed",
            "quote_needed",
            "notes",
        ])
        for stop in plan.get("stops", []):
            writer.writerow([
                self.core._csv_cell(stop.get("sequence_no")),
                self.core._csv_cell(stop.get("customer_name")),
                self.core._csv_cell(stop.get("city")),
                self.core._csv_cell(stop.get("country")),
                self.core._csv_cell(stop.get("lead_display_id")),
                self.core._csv_cell(stop.get("lead_title")),
                self.core._csv_cell(stop.get("sales_stage")),
                self.core._csv_cell(stop.get("lead_owner_name")),
                self.core._num(stop.get("deal_amount")) or self.core._num(stop.get("estimated_value")),
                self.core._csv_cell(stop.get("planned_date")),
                self.core._csv_cell(stop.get("planned_end_date")),
                self.core._csv_cell(stop.get("stay_days") or 1),
                self.core._csv_cell(stop.get("travel_from_label")),
                self.core._csv_cell(stop.get("travel_mode")),
                self.core._csv_cell(stop.get("travel_distance_km")),
                self.core._csv_cell(stop.get("travel_time_hours")),
                self.core._csv_cell(stop.get("travel_days")),
                self.core._csv_cell(stop.get("visit_purpose")),
                self.core._csv_cell(stop.get("result_status")),
                self.core._csv_cell(stop.get("result_notes")),
                self.core._csv_cell(stop.get("visit_customer_needs")),
                self.core._csv_cell(stop.get("visit_competitor")),
                self.core._csv_cell(stop.get("visit_budget")),
                self.core._csv_cell(stop.get("visit_decision_maker")),
                self.core._csv_cell(stop.get("visit_next_action")),
                self.core._csv_cell("Yes" if stop.get("visit_sample_needed") else "No"),
                self.core._csv_cell("Yes" if stop.get("visit_quote_needed") else "No"),
                self.core._csv_cell(stop.get("notes")),
            ])
        return output.getvalue()
