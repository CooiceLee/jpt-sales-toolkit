"""Persistence helpers for non-customer Trip Planner stops."""

from __future__ import annotations


FREE_STOP_CATEGORIES = {"rest", "hotel", "airport", "transit", "meal", "other"}


class TripFreeStopRepository:
    def __init__(self, conn):
        self.conn = conn

    def list_active(self, plan_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT * FROM trip_plan_free_stops
            WHERE plan_id = ? AND archived_at IS NULL
            ORDER BY sequence_no, created_at, id
            """,
            (plan_id,),
        ).fetchall()
        return [self.normalize(dict(row)) for row in rows]

    def get_active(self, free_stop_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM trip_plan_free_stops "
            "WHERE id = ? AND archived_at IS NULL",
            (free_stop_id,),
        ).fetchone()
        return self.normalize(dict(row)) if row else None

    @staticmethod
    def normalize(item: dict) -> dict:
        """Expose the shared stop shape without inventing customer records."""
        item["stop_kind"] = "free"
        item["customer_name"] = item.get("location_name")
        item["result_status"] = None
        item["result_notes"] = None
        item["lead_id"] = None
        item["customer_id"] = None
        return item

    def next_sequence(self, plan_id: str) -> int:
        row = self.conn.execute(
            """
            SELECT COALESCE(MAX(sequence_no), 0) + 1
            FROM (
                SELECT sequence_no FROM trip_plan_stops
                WHERE plan_id = ? AND archived_at IS NULL
                UNION ALL
                SELECT sequence_no FROM trip_plan_free_stops
                WHERE plan_id = ? AND archived_at IS NULL
            )
            """,
            (plan_id, plan_id),
        ).fetchone()
        return int(row[0] or 1)

    def normalize_sequences(self, plan_id: str, actor_id: str, timestamp: str) -> None:
        rows = self.active_references(plan_id)
        self.set_order(plan_id, [row["id"] for row in rows], actor_id, timestamp)

    def active_references(self, plan_id: str) -> list[dict]:
        return [
            dict(row)
            for row in self.conn.execute(
            """
            SELECT id, stop_kind FROM (
                SELECT id, sequence_no, created_at, 'customer' AS stop_kind
                FROM trip_plan_stops
                WHERE plan_id = ? AND archived_at IS NULL
                UNION ALL
                SELECT id, sequence_no, created_at, 'free' AS stop_kind
                FROM trip_plan_free_stops
                WHERE plan_id = ? AND archived_at IS NULL
            )
            ORDER BY sequence_no, created_at, id
            """,
            (plan_id, plan_id),
            ).fetchall()
        ]

    def set_order(
        self,
        plan_id: str,
        stop_ids: list[str],
        actor_id: str,
        timestamp: str,
    ) -> None:
        by_id = {row["id"]: row for row in self.active_references(plan_id)}
        for sequence_no, stop_id in enumerate(stop_ids, start=1):
            row = by_id[stop_id]
            table = (
                "trip_plan_free_stops"
                if row["stop_kind"] == "free"
                else "trip_plan_stops"
            )
            self.conn.execute(
                f"""
                UPDATE {table}
                SET sequence_no = ?, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE id = ?
                """,
                (sequence_no, timestamp, actor_id, stop_id),
            )
