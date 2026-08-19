"""Minimal role-scoped task workload aggregates."""

from __future__ import annotations

from .base import BaseRepository


class TaskWorkloadRepository(BaseRepository):
    """Count active task-bearing leads without returning business records."""

    def count_active_leads_for_tech(self, tech_id: str) -> dict[str, int]:
        """Return distinct active lead counts for one technical assignee.

        A task contributes only while the task, its lead, and its customer are
        all active. Completed/cancelled pre-sales work and resolved/closed
        after-sales work are deliberately excluded from navigation workload.
        """
        row = self.conn.execute(
            """
            WITH assigned_tasks AS (
                SELECT 'pre_sales' AS task_type, lead_id, status
                FROM pre_sales_tasks
                WHERE assignee_id = ? AND archived_at IS NULL
                UNION ALL
                SELECT 'after_sales' AS task_type, lead_id, status
                FROM after_sales_tasks
                WHERE assignee_id = ? AND archived_at IS NULL
            )
            SELECT
                COUNT(DISTINCT CASE
                    WHEN assigned_tasks.task_type = 'pre_sales'
                     AND assigned_tasks.status IN ('Open', 'In Progress')
                    THEN assigned_tasks.lead_id
                END) AS pre_sales_active_lead_count,
                COUNT(DISTINCT CASE
                    WHEN assigned_tasks.task_type = 'after_sales'
                     AND assigned_tasks.status IN ('Open', 'In Progress')
                    THEN assigned_tasks.lead_id
                END) AS after_sales_active_lead_count
            FROM assigned_tasks
            JOIN leads ON leads.id = assigned_tasks.lead_id
                      AND leads.archived_at IS NULL
            JOIN customers ON customers.id = leads.customer_id
                          AND customers.archived_at IS NULL
            """,
            (tech_id, tech_id),
        ).fetchone()
        return {
            "pre_sales_active_lead_count": int(row[0] or 0),
            "after_sales_active_lead_count": int(row[1] or 0),
        }
