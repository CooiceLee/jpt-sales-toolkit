"""Persistence boundary for first-class Trip Planner legs."""

from __future__ import annotations

from ..repositories.base import generate_uuid


class TripLegRepository:
    def __init__(self, conn):
        self.conn = conn

    def list_active(self, plan_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM trip_plan_legs
            WHERE plan_id = ? AND archived_at IS NULL
            ORDER BY sequence_no, created_at, id
            """,
            (plan_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["from_customer_stop_id"] = item.get("from_stop_id")
            item["to_customer_stop_id"] = item.get("to_stop_id")
            item["from_stop_id"] = (
                item.get("from_stop_id") or item.get("from_free_stop_id")
            )
            item["to_stop_id"] = item.get("to_stop_id") or item.get("to_free_stop_id")
            item["from_stop_kind"] = (
                "free" if item.get("from_free_stop_id") else
                "customer" if item.get("from_stop_id") else None
            )
            item["to_stop_kind"] = (
                "free" if item.get("to_free_stop_id") else
                "customer" if item.get("to_stop_id") else None
            )
            item["member_id"] = item.get("member_id")
            item["mode_locked"] = bool(item.get("mode_locked"))
            item["mode"] = item.get("selected_mode")
            item["from"] = item.get("from_label")
            item["to"] = item.get("to_label")
            result.append(item)
        return result

    def saved_airports(self, plan_id: str) -> dict[tuple, dict]:
        """Return the most recent airports recorded for each leg key.

        Unlike locked overrides these survive a plain regeneration: choosing an
        airport is real work and must not require locking the leg as well.
        """
        rows = self.conn.execute(
            """
            SELECT * FROM trip_plan_legs
            WHERE plan_id = ?
            ORDER BY member_id, leg_key,
                     (archived_at IS NULL) DESC,
                     updated_at DESC, created_at DESC, id DESC
            """,
            (plan_id,),
        ).fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            leg = dict(row)
            key = (leg.get("member_id"), leg["leg_key"])
            if key in result:
                continue
            saved = {
                field: leg.get(field)
                for field in (
                    "departure_airport_name",
                    "departure_airport_lat",
                    "departure_airport_lng",
                    "departure_airport_stay_half_days",
                    "arrival_airport_name",
                    "arrival_airport_lat",
                    "arrival_airport_lng",
                    "arrival_airport_stay_half_days",
                )
            }
            if saved.get("departure_airport_name") or saved.get("arrival_airport_name"):
                result[key] = saved
        return result

    def locked_overrides(self, plan_id: str) -> dict[tuple, dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM trip_plan_legs
            WHERE plan_id = ?
            ORDER BY member_id, leg_key,
                     (archived_at IS NULL) DESC,
                     updated_at DESC, created_at DESC, id DESC
            """,
            (plan_id,),
        ).fetchall()
        result = {}
        seen = set()
        for row in rows:
            leg = dict(row)
            key = (leg.get("member_id"), leg["leg_key"])
            if key in seen:
                continue
            seen.add(key)
            if not leg.get("mode_locked"):
                continue
            result[key] = {
                "selected_mode": leg["selected_mode"],
                "mode_locked": True,
                "manual_distance_km": leg.get("manual_distance_km"),
                "manual_time_hours": leg.get("manual_time_hours"),
                "manual_travel_days": leg.get("manual_travel_days"),
                "manual_travel_half_days": leg.get("manual_travel_half_days"),
                "notes": leg.get("notes"),
            }
        return result

    def archive_active(self, plan_id: str, actor_id: str, timestamp: str) -> None:
        """Archive current route legs without committing the caller's transaction."""
        self.conn.execute(
            """
            UPDATE trip_plan_legs
            SET archived_at = ?, updated_at = ?, updated_by = ?,
                row_version = row_version + 1
            WHERE plan_id = ? AND archived_at IS NULL
            """,
            (timestamp, timestamp, actor_id, plan_id),
        )

    def trip_member_ids(self, plan_id: str) -> set:
        """User ids recorded as travelling on this plan."""
        return {
            row[0]
            for row in self.conn.execute(
                "SELECT user_id FROM trip_plan_members WHERE plan_id = ?",
                (plan_id,),
            )
        }

    def replace_active(
        self,
        plan_id: str,
        legs: list[dict],
        actor_id: str,
        timestamp: str,
    ) -> None:
        self.archive_active(plan_id, actor_id, timestamp)
        # Foreign keys are not enforced in this database, so a leg attributed to
        # somebody who is not on the trip has to be refused here or it would be
        # stored and then read back as an unexplainable traveller.
        members = self.trip_member_ids(plan_id)
        for leg in legs:
            member_id = leg.get("member_id")
            if member_id is not None and member_id not in members:
                raise ValueError(
                    f"Leg {leg.get('leg_key')} is assigned to somebody who is "
                    "not a member of this trip"
                )
        for leg in legs:
            self.conn.execute(
                """
                INSERT INTO trip_plan_legs (
                    id, plan_id, member_id, leg_key, sequence_no,
                    from_kind, from_stop_id, from_free_stop_id, from_label,
                    to_kind, to_stop_id, to_free_stop_id, to_label,
                    selected_mode, mode_locked,
                    distance_km, time_hours, travel_days,
                    travel_half_days,
                    manual_distance_km, manual_time_hours,
                    manual_travel_days, manual_travel_half_days,
                    planned_start_date, planned_start_period,
                    planned_end_date, planned_end_period, notes,
                    departure_airport_name, departure_airport_lat,
                    departure_airport_lng, departure_airport_stay_half_days,
                    arrival_airport_name, arrival_airport_lat,
                    arrival_airport_lng, arrival_airport_stay_half_days,
                    created_at, created_by, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?)
                """,
                (
                    generate_uuid(),
                    plan_id,
                    leg.get("member_id"),
                    leg["leg_key"],
                    leg["sequence_no"],
                    leg["from_kind"],
                    (
                        leg.get("from_stop_id")
                        if leg.get("from_stop_kind") != "free" else None
                    ),
                    (
                        leg.get("from_stop_id")
                        if leg.get("from_stop_kind") == "free" else None
                    ),
                    leg.get("from_label"),
                    leg["to_kind"],
                    (
                        leg.get("to_stop_id")
                        if leg.get("to_stop_kind") != "free" else None
                    ),
                    (
                        leg.get("to_stop_id")
                        if leg.get("to_stop_kind") == "free" else None
                    ),
                    leg.get("to_label"),
                    leg["selected_mode"],
                    1 if leg.get("mode_locked") else 0,
                    leg["distance_km"],
                    leg["time_hours"],
                    leg["travel_days"],
                    leg["travel_half_days"],
                    leg.get("manual_distance_km"),
                    leg.get("manual_time_hours"),
                    leg.get("manual_travel_days"),
                    leg.get("manual_travel_half_days"),
                    leg.get("planned_start_date"),
                    leg.get("planned_start_period"),
                    leg.get("planned_end_date"),
                    leg.get("planned_end_period"),
                    leg.get("notes"),
                    leg.get("departure_airport_name"),
                    leg.get("departure_airport_lat"),
                    leg.get("departure_airport_lng"),
                    int(leg.get("departure_airport_stay_half_days") or 0),
                    leg.get("arrival_airport_name"),
                    leg.get("arrival_airport_lat"),
                    leg.get("arrival_airport_lng"),
                    int(leg.get("arrival_airport_stay_half_days") or 0),
                    timestamp,
                    actor_id,
                    timestamp,
                    actor_id,
                ),
            )
