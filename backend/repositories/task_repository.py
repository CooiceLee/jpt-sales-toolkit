"""
Task repositories - database operations for pre_sales_tasks and after_sales_tasks.
"""

from __future__ import annotations

from typing import Optional

from .base import BaseRepository, ConflictError, generate_uuid, now_iso


class PreSalesTaskRepository(BaseRepository):
    """Repository for pre_sales_tasks table."""

    table_name = "pre_sales_tasks"

    def create(self, lead_id: str, data: dict, actor_id: str) -> str:
        """Create new pre-sales task. Returns task ID."""
        task_id = generate_uuid()
        now = now_iso()

        insert_data = {
            "id": task_id,
            "lead_id": lead_id,
            "status": "Open",
            "created_at": now,
            "created_by": actor_id,
            "updated_at": now,
            "updated_by": actor_id,
            "row_version": 1,
            **data,
        }

        sql, params = self._build_insert(insert_data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return task_id

    def update(
        self,
        task_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
    ) -> dict:
        """Update task with optimistic locking."""
        current = self.get_by_id(task_id)
        if not current:
            raise ValueError(f"PreSalesTask {task_id} not found")
        if current.get("archived_at"):
            raise ValueError("Archived pre-sales tasks must be restored before editing")

        if current["row_version"] != row_version:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": task_id, "updated_at": current["updated_at"]},
            )

        update_data = {
            **data,
            "updated_at": now_iso(),
            "updated_by": actor_id,
            "row_version": row_version + 1,
        }

        sql, params = self._build_update(task_id, update_data, row_version)
        cursor = self.conn.execute(sql, params)

        if cursor.rowcount == 0:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": task_id, "updated_at": current["updated_at"]},
            )

        self.conn.commit()
        return self.get_by_id(task_id)

    def list(self, filters: Optional[dict] = None) -> list[dict]:
        """List pre-sales tasks with filters."""
        filters = filters or {}
        sql = """
            SELECT DISTINCT t.*, l.display_id as lead_display_id, l.title as lead_title,
                   u.display_name as assignee_name
            FROM pre_sales_tasks t
            JOIN leads l ON t.lead_id = l.id
            LEFT JOIN users u ON t.assignee_id = u.id
            LEFT JOIN lead_assignments la
                ON l.id = la.lead_id AND la.archived_at IS NULL
            WHERE l.archived_at IS NULL
        """
        params: list = []

        if not filters.get("include_archived"):
            sql += " AND t.archived_at IS NULL"

        if filters.get("lead_id"):
            sql += " AND t.lead_id = ?"
            params.append(filters["lead_id"])

        if filters.get("assignee_id"):
            sql += " AND t.assignee_id = ?"
            params.append(filters["assignee_id"])

        if filters.get("status"):
            sql += " AND t.status = ?"
            params.append(filters["status"])

        if filters.get("visible_to_user_id"):
            sql += " AND (l.owner_id = ? OR la.user_id = ?)"
            params.extend([filters["visible_to_user_id"]] * 2)

        sql += " ORDER BY t.created_at DESC LIMIT ? OFFSET ?"
        params.extend([filters.get("limit", 100), filters.get("offset", 0)])

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def archive(self, task_id: str, actor_id: str) -> bool:
        """Archive pre-sales task."""
        cursor = self.conn.execute(
            """
            UPDATE pre_sales_tasks
            SET archived_at = ?, updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ? AND archived_at IS NULL
            """,
            (now_iso(), now_iso(), actor_id, task_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def restore(self, task_id: str, actor_id: str) -> bool:
        """Restore archived pre-sales task."""
        cursor = self.conn.execute(
            """
            UPDATE pre_sales_tasks
            SET archived_at = NULL, updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ? AND archived_at IS NOT NULL
            """,
            (now_iso(), actor_id, task_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def list_for_lead(self, lead_id: str) -> list[dict]:
        """Get all tasks for a specific lead."""
        cursor = self.conn.execute(
            """
            SELECT t.*, u.display_name as assignee_name
            FROM pre_sales_tasks t
            LEFT JOIN users u ON t.assignee_id = u.id
            WHERE t.lead_id = ? AND t.archived_at IS NULL
            ORDER BY t.created_at DESC
            """,
            (lead_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


class AfterSalesTaskRepository(BaseRepository):
    """Repository for after_sales_tasks table."""

    table_name = "after_sales_tasks"

    def create(
        self,
        lead_id: str,
        data: dict,
        actor_id: str,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> str:
        """Create new after-sales task. Returns task ID."""
        task_id = generate_uuid()
        now = now_iso()
        created = created_at or now
        updated = updated_at or created

        insert_data = {
            "id": task_id,
            "lead_id": lead_id,
            "status": "Open",
            "created_at": created,
            "created_by": actor_id,
            "updated_at": updated,
            "updated_by": actor_id,
            "row_version": 1,
            **data,
        }

        sql, params = self._build_insert(insert_data)
        self.conn.execute(sql, params)
        self.conn.commit()
        return task_id

    def update(
        self,
        task_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
    ) -> dict:
        """Update task with optimistic locking."""
        current = self.get_by_id(task_id)
        if not current:
            raise ValueError(f"AfterSalesTask {task_id} not found")
        if current.get("archived_at"):
            raise ValueError("Archived after-sales tasks must be restored before editing")

        if current["row_version"] != row_version:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": task_id, "updated_at": current["updated_at"]},
            )

        update_data = {
            **data,
            "updated_at": now_iso(),
            "updated_by": actor_id,
            "row_version": row_version + 1,
        }

        sql, params = self._build_update(task_id, update_data, row_version)
        cursor = self.conn.execute(sql, params)

        if cursor.rowcount == 0:
            raise ConflictError(
                current_version=current["row_version"],
                your_version=row_version,
                current_data={"id": task_id, "updated_at": current["updated_at"]},
            )

        self.conn.commit()
        return self.get_by_id(task_id)

    def archive(self, task_id: str, actor_id: str) -> bool:
        """Archive after-sales task."""
        cursor = self.conn.execute(
            """
            UPDATE after_sales_tasks
            SET archived_at = ?, updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ? AND archived_at IS NULL
            """,
            (now_iso(), now_iso(), actor_id, task_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def restore(self, task_id: str, actor_id: str) -> bool:
        """Restore archived after-sales task."""
        cursor = self.conn.execute(
            """
            UPDATE after_sales_tasks
            SET archived_at = NULL, updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ? AND archived_at IS NOT NULL
            """,
            (now_iso(), actor_id, task_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def list(self, filters: Optional[dict] = None) -> list[dict]:
        """List after-sales tasks with filters."""
        filters = filters or {}
        sql = """
            SELECT DISTINCT t.*, l.display_id as lead_display_id, l.title as lead_title,
                   u.display_name as assignee_name
            FROM after_sales_tasks t
            JOIN leads l ON t.lead_id = l.id
            LEFT JOIN users u ON t.assignee_id = u.id
            LEFT JOIN lead_assignments la
                ON l.id = la.lead_id AND la.archived_at IS NULL
            WHERE l.archived_at IS NULL
        """
        params: list = []

        if not filters.get("include_archived"):
            sql += " AND t.archived_at IS NULL"

        if filters.get("lead_id"):
            sql += " AND t.lead_id = ?"
            params.append(filters["lead_id"])

        if filters.get("assignee_id"):
            sql += " AND t.assignee_id = ?"
            params.append(filters["assignee_id"])

        if filters.get("status"):
            sql += " AND t.status = ?"
            params.append(filters["status"])

        if filters.get("visible_to_user_id"):
            sql += " AND (l.owner_id = ? OR la.user_id = ?)"
            params.extend([filters["visible_to_user_id"]] * 2)

        sql += " ORDER BY t.created_at DESC LIMIT ? OFFSET ?"
        params.extend([filters.get("limit", 100), filters.get("offset", 0)])

        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def list_for_lead(self, lead_id: str) -> list[dict]:
        """Get all tasks for a specific lead."""
        cursor = self.conn.execute(
            """
            SELECT t.*, u.display_name as assignee_name
            FROM after_sales_tasks t
            LEFT JOIN users u ON t.assignee_id = u.id
            WHERE t.lead_id = ? AND t.archived_at IS NULL
            ORDER BY t.created_at DESC
            """,
            (lead_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
