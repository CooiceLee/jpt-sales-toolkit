"""Batch read model for the latest visible formal lead follow-up."""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository


class FollowUpReadRepository(BaseRepository):
    """Read the latest follow-up without per-lead queries."""

    def latest_by_lead(
        self,
        lead_ids: list[str],
        actor_id: Optional[str] = None,
        actor_role: str = "leader",
    ) -> dict[str, dict]:
        if not lead_ids:
            return {}

        placeholders = ", ".join("?" * len(lead_ids))
        visibility_sql, visibility_params = self._visibility(actor_id, actor_role)
        cursor = self.conn.execute(
            f"""
            WITH ranked_follow_ups AS (
                SELECT
                    a.*, u.display_name AS actor_name,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.lead_id
                        ORDER BY a.created_at DESC, a.id DESC
                    ) AS follow_up_rank
                FROM lead_activities a
                JOIN leads l ON l.id = a.lead_id
                LEFT JOIN users u ON u.id = a.actor_id
                WHERE a.lead_id IN ({placeholders})
                  AND a.action_type = 'follow_up'
                  AND a.is_formal_follow_up = 1
                  AND a.archived_at IS NULL
                  AND l.archived_at IS NULL
                  {visibility_sql}
            )
            SELECT * FROM ranked_follow_ups WHERE follow_up_rank = 1
            """,
            [*lead_ids, *visibility_params],
        )
        result = {}
        for row in cursor.fetchall():
            item = dict(row)
            item.pop("follow_up_rank", None)
            result[item["lead_id"]] = item
        return result

    @staticmethod
    def _visibility(
        actor_id: Optional[str], actor_role: str
    ) -> tuple[str, list[str]]:
        if actor_role == "leader" or not actor_id:
            return "", []
        if actor_role in {"owner", "collaborator"}:
            return "AND a.visibility IN ('all', 'internal')", []
        if actor_role in {"tech", "watcher"}:
            return "AND a.visibility = 'all'", []
        return """
            AND (
                a.visibility = 'all'
                OR (
                    a.visibility = 'internal'
                    AND (
                        l.owner_id = ?
                        OR EXISTS (
                            SELECT 1 FROM lead_assignments visible_assignment
                            WHERE visible_assignment.lead_id = l.id
                              AND visible_assignment.user_id = ?
                              AND visible_assignment.assignment_type
                                  IN ('owner', 'collaborator')
                              AND visible_assignment.archived_at IS NULL
                        )
                    )
                )
            )
        """, [actor_id, actor_id]
