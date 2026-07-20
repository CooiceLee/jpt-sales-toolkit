"""Permission-scoped pre-sales workload counts."""

from __future__ import annotations

from .base import BaseRepository


class PreSalesReadRepository(BaseRepository):
    """Read aggregate pre-sales work without exposing task records."""

    def count_active_leads(self, actor_id: str, actor_role: str) -> int:
        sql = """
            SELECT COUNT(DISTINCT t.lead_id)
            FROM pre_sales_tasks t
            JOIN leads l ON l.id = t.lead_id
            JOIN customers c ON c.id = l.customer_id
            WHERE t.archived_at IS NULL
              AND t.status IN ('Open', 'In Progress')
              AND l.archived_at IS NULL
              AND c.archived_at IS NULL
        """
        params: list[str] = []
        if actor_role == "tech":
            sql += " AND t.assignee_id = ?"
            params.append(actor_id)
        elif actor_role != "leader":
            sql += """
                AND (
                    l.owner_id = ?
                    OR EXISTS (
                        SELECT 1 FROM lead_assignments visible_assignment
                        WHERE visible_assignment.lead_id = l.id
                          AND visible_assignment.user_id = ?
                          AND visible_assignment.archived_at IS NULL
                    )
                )
            """
            params.extend([actor_id, actor_id])
        return int(self.conn.execute(sql, params).fetchone()[0])
