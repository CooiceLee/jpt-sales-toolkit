"""
Activity repository - database operations for lead_activities.
"""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, generate_uuid, now_iso


class ActivityRepository(BaseRepository):
    """Repository for lead_activities table."""

    table_name = "lead_activities"

    def create(
        self,
        lead_id: str,
        actor_id: str,
        action_type: str,
        summary: str,
        payload_json: Optional[str] = None,
        visibility: str = "all",
        is_formal_follow_up: bool = False,
        changed_field: Optional[str] = None,
        before_value: Optional[str] = None,
        after_value: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        """Create new activity. Returns activity ID."""
        activity_id = generate_uuid()

        self.conn.execute(
            """
            INSERT INTO lead_activities (
                id, lead_id, actor_id, action_type, visibility,
                is_formal_follow_up, summary, payload_json,
                changed_field, before_value, after_value, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                lead_id,
                actor_id,
                action_type,
                visibility,
                1 if is_formal_follow_up else 0,
                summary,
                payload_json,
                changed_field,
                before_value,
                after_value,
                created_at or now_iso(),
            ),
        )
        self.conn.commit()
        return activity_id

    def list_for_lead(
        self,
        lead_id: str,
        limit: int = 50,
        offset: int = 0,
        action_type: Optional[str] = None,
        visibility_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        """List activities for a lead with pagination."""
        sql = """
            SELECT a.*, u.display_name as actor_name
            FROM lead_activities a
            LEFT JOIN users u ON a.actor_id = u.id
            WHERE a.lead_id = ?
        """
        params: list = [lead_id]

        sql += " AND a.archived_at IS NULL"

        if action_type:
            sql += " AND a.action_type = ?"
            params.append(action_type)

        if visibility_filter:
            placeholders = ", ".join("?" * len(visibility_filter))
            sql += f" AND a.visibility IN ({placeholders})"
            params.extend(visibility_filter)

        sql += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def list_all_for_lead(
        self,
        lead_id: str,
        action_type: Optional[str] = None,
        visibility_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        """List all active activities for export and merge operations."""
        return self.list_for_lead(
            lead_id=lead_id,
            limit=100000,
            offset=0,
            action_type=action_type,
            visibility_filter=visibility_filter,
        )

    def count_for_lead(self, lead_id: str) -> int:
        """Count activities for a lead."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM lead_activities WHERE lead_id = ? AND archived_at IS NULL",
            (lead_id,),
        )
        return cursor.fetchone()[0]

    def count_follow_ups_for_lead(self, lead_id: str) -> int:
        """Count active formal follow-up records for a lead."""
        cursor = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM lead_activities
            WHERE lead_id = ?
              AND action_type = 'follow_up'
              AND archived_at IS NULL
            """,
            (lead_id,),
        )
        return cursor.fetchone()[0]

    def count_follow_ups_by_lead(self, lead_ids: list[str]) -> dict[str, int]:
        """Count active formal follow-up records for multiple leads."""
        if not lead_ids:
            return {}

        placeholders = ", ".join("?" * len(lead_ids))
        cursor = self.conn.execute(
            f"""
            SELECT lead_id, COUNT(*) AS count
            FROM lead_activities
            WHERE lead_id IN ({placeholders})
              AND action_type = 'follow_up'
              AND archived_at IS NULL
            GROUP BY lead_id
            """,
            lead_ids,
        )
        return {row["lead_id"]: row["count"] for row in cursor.fetchall()}

    def update(self, activity_id: str, data: dict) -> Optional[dict]:
        """Update editable activity fields."""
        if not data:
            return self.get_by_id(activity_id)

        allowed = {
            "summary",
            "payload_json",
            "visibility",
            "created_at",
        }
        update_data = {key: value for key, value in data.items() if key in allowed}
        if not update_data:
            return self.get_by_id(activity_id)

        sql, params = self._build_update(activity_id, update_data)
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_by_id(activity_id)

    def get_recent_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        """Get recent activities involving a user."""
        cursor = self.conn.execute(
            """
            SELECT a.*, u.display_name as actor_name, l.display_id as lead_display_id, l.title as lead_title
            FROM lead_activities a
            LEFT JOIN users u ON a.actor_id = u.id
            JOIN leads l ON a.lead_id = l.id
            WHERE a.archived_at IS NULL
              AND l.archived_at IS NULL
              AND (a.actor_id = ? OR l.owner_id = ?)
            ORDER BY a.created_at DESC
            LIMIT ?
            """,
            (user_id, user_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def archive(self, activity_id: str) -> bool:
        """Soft archive an activity."""
        cursor = self.conn.execute(
            """
            UPDATE lead_activities
            SET archived_at = ?
            WHERE id = ? AND archived_at IS NULL
            """,
            (now_iso(), activity_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def restore(self, activity_id: str) -> bool:
        """Restore an archived activity."""
        cursor = self.conn.execute(
            """
            UPDATE lead_activities
            SET archived_at = NULL
            WHERE id = ? AND archived_at IS NOT NULL
            """,
            (activity_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def archive_task_updates(self, task_id: str, task_type: str) -> int:
        """Archive task-related activity records."""
        cursor = self.conn.execute(
            """
            UPDATE lead_activities
            SET archived_at = ?
            WHERE archived_at IS NULL
              AND action_type = 'task_update'
              AND payload_json LIKE ?
              AND payload_json LIKE ?
            """,
            (now_iso(), f'%"task_type": "{task_type}"%', f'%"task_id": "{task_id}"%'),
        )
        self.conn.commit()
        return cursor.rowcount

    def restore_task_updates(self, task_id: str, task_type: str) -> int:
        """Restore archived task-related activity records."""
        cursor = self.conn.execute(
            """
            UPDATE lead_activities
            SET archived_at = NULL
            WHERE archived_at IS NOT NULL
              AND action_type = 'task_update'
              AND payload_json LIKE ?
              AND payload_json LIKE ?
            """,
            (f'%"task_type": "{task_type}"%', f'%"task_id": "{task_id}"%'),
        )
        self.conn.commit()
        return cursor.rowcount

    def get_follow_ups_due(
        self,
        before_date: str,
        owner_id: Optional[str] = None,
    ) -> list[dict]:
        """Get leads with follow-ups due before a date."""
        sql = """
            SELECT l.*, c.display_name as customer_name
            FROM leads l
            JOIN customers c ON l.customer_id = c.id
            WHERE l.archived_at IS NULL
              AND l.next_followup_date IS NOT NULL
              AND l.next_followup_date <= ?
              AND l.sales_stage NOT IN ('Won', 'Lost')
        """
        params: list = [before_date]

        if owner_id:
            sql += " AND l.owner_id = ?"
            params.append(owner_id)

        sql += " ORDER BY l.next_followup_date ASC"

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
