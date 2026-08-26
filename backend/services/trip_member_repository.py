"""Who is travelling on a trip plan, and from where.

Members are existing team accounts: planning only covers people the company can
actually send. A member may leave from and return to their own place, and when
they do not, the plan's own origin and destination apply.
"""

from __future__ import annotations

from ..repositories.base import generate_uuid, now_iso

OVERRIDE_FIELDS = (
    "origin_name_override",
    "origin_lat_override",
    "origin_lng_override",
    "destination_name_override",
    "destination_lat_override",
    "destination_lng_override",
)


class TripMemberRepository:
    def __init__(self, conn):
        self.conn = conn

    def list_active(self, plan_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT m.*, u.display_name AS display_name, u.role AS role
            FROM trip_plan_members m
            JOIN users u ON m.user_id = u.id
            WHERE m.plan_id = ?
            ORDER BY m.created_at, m.id
            """,
            (plan_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def member_ids(self, plan_id: str) -> tuple:
        return tuple(item["user_id"] for item in self.list_active(plan_id))

    def is_team_account(self, user_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()
        return row is not None

    def add(self, plan_id: str, user_id: str, overrides: dict,
            actor_id: str) -> dict | None:
        """Put an existing account on the trip. Adding twice changes nothing."""
        if not self.is_team_account(user_id):
            return None
        existing = self.conn.execute(
            "SELECT id FROM trip_plan_members WHERE plan_id = ? AND user_id = ?",
            (plan_id, user_id),
        ).fetchone()
        if existing:
            return self.update(existing["id"], overrides, actor_id)
        now = now_iso()
        values = [(overrides or {}).get(field) for field in OVERRIDE_FIELDS]
        member_id = generate_uuid()
        self.conn.execute(
            f"""
            INSERT INTO trip_plan_members (
                id, plan_id, user_id, {", ".join(OVERRIDE_FIELDS)},
                created_at, created_by, updated_at, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (member_id, plan_id, user_id, *values, now, actor_id, now, actor_id),
        )
        self.conn.commit()
        return self.get(member_id)

    def update(self, member_id: str, overrides: dict, actor_id: str) -> dict | None:
        changes = {
            field: (overrides or {}).get(field)
            for field in OVERRIDE_FIELDS
            if field in (overrides or {})
        }
        if not changes:
            return self.get(member_id)
        assignments = ", ".join(f"{field} = ?" for field in changes)
        self.conn.execute(
            f"""
            UPDATE trip_plan_members
            SET {assignments}, updated_at = ?, updated_by = ?,
                row_version = row_version + 1
            WHERE id = ?
            """,
            (*changes.values(), now_iso(), actor_id, member_id),
        )
        self.conn.commit()
        return self.get(member_id)

    def get(self, member_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM trip_plan_members WHERE id = ?", (member_id,)
        ).fetchone()
        return dict(row) if row else None

    def remove(self, plan_id: str, user_id: str) -> bool:
        """Take somebody off the trip, along with the route worked out for them."""
        cursor = self.conn.execute(
            "DELETE FROM trip_plan_members WHERE plan_id = ? AND user_id = ?",
            (plan_id, user_id),
        )
        if cursor.rowcount:
            self.conn.execute(
                "UPDATE trip_plan_legs SET archived_at = ? "
                "WHERE plan_id = ? AND member_id = ? AND archived_at IS NULL",
                (now_iso(), plan_id, user_id),
            )
        self.conn.commit()
        return bool(cursor.rowcount)

    def points(self, plan_id: str, plan: dict) -> tuple:
        """Each member's departure and return points, falling back to the plan."""
        origins = {}
        destinations = {}
        if plan.get("origin_lat") is not None:
            origins["__default__"] = {
                "lat": plan.get("origin_lat"), "lng": plan.get("origin_lng"),
                "label": plan.get("origin_name"), "kind": "origin",
                "stop_id": None,
            }
        if plan.get("destination_lat") is not None:
            destinations["__default__"] = {
                "lat": plan.get("destination_lat"),
                "lng": plan.get("destination_lng"),
                "label": plan.get("destination_name"),
                "kind": "destination", "stop_id": None,
            }
        for member in self.list_active(plan_id):
            user_id = member["user_id"]
            if member.get("origin_lat_override") is not None:
                origins[user_id] = {
                    "lat": member["origin_lat_override"],
                    "lng": member["origin_lng_override"],
                    "label": member.get("origin_name_override"),
                    "kind": "origin", "stop_id": None,
                }
            if member.get("destination_lat_override") is not None:
                destinations[user_id] = {
                    "lat": member["destination_lat_override"],
                    "lng": member["destination_lng_override"],
                    "label": member.get("destination_name_override"),
                    "kind": "destination", "stop_id": None,
                }
        return origins, destinations
