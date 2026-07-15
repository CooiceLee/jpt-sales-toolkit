"""Permission-aware imported-data quality prompt workflow."""

from __future__ import annotations

from typing import Optional

from ..repositories.data_quality_issue_repository import DataQualityIssueRepository


class DataQualityIssueService:
    def __init__(self, repository: Optional[DataQualityIssueRepository] = None):
        self.repository = repository or DataQualityIssueRepository()
        self.conn = self.repository.conn

    def list(self, actor: dict, filters: Optional[dict] = None) -> list[dict]:
        filters = filters or {}
        rows = self.repository.list_with_bindings(
            status=filters.get("status", "open"),
            entity_type=filters.get("entity_type"),
            entity_id=filters.get("entity_id"),
            limit=filters.get("limit", 200),
        )
        return [item for item in rows if self._can_access(item, actor)]

    def update(self, issue_id: str, status: str, note: str, actor: dict) -> dict:
        if status not in {"open", "resolved", "ignored"}:
            raise ValueError("Quality issue status must be open, resolved, or ignored")
        issue = self.repository.get_with_binding(issue_id)
        if not issue:
            raise LookupError("Data quality issue was not found")
        if not self._can_access(issue, actor):
            raise PermissionError("Data quality issue is outside this account's scope")
        if status == "ignored" and actor.get("role") != "leader":
            raise PermissionError("Only a Leader can ignore data quality issues")
        return self.repository.set_status(issue_id, status, note, actor["id"])

    def counts_for_leads(self, lead_ids: list[str]) -> dict[str, int]:
        return self.repository.open_counts_for_leads(lead_ids)

    def _can_access(self, issue: dict, actor: dict) -> bool:
        if actor.get("role") == "leader":
            return True
        entity_type, entity_id = issue.get("entity_type"), issue.get("local_entity_id")
        if not entity_type or not entity_id:
            return False
        if entity_type in {"customers", "contacts", "aliases"}:
            customer_id = self._customer_id(entity_type, entity_id)
            return (
                actor.get("role") == "sales"
                and bool(customer_id)
                and self._customer_visible(customer_id, actor["id"])
            )
        lead_id, assignee_id = self._lead_context(entity_type, entity_id)
        if actor.get("role") == "tech":
            return entity_type in {"pre_sales_tasks", "after_sales_tasks"} and assignee_id == actor["id"]
        return actor.get("role") == "sales" and bool(lead_id) and self._lead_visible(lead_id, actor["id"])

    def _customer_visible(self, customer_id: str, user_id: str) -> bool:
        return self.conn.execute(
            """SELECT 1 FROM leads l
               JOIN customers c ON c.id = l.customer_id
               LEFT JOIN lead_assignments a
                 ON a.lead_id = l.id AND a.user_id = ?
                AND a.assignment_type = 'collaborator' AND a.archived_at IS NULL
               WHERE l.customer_id = ? AND l.archived_at IS NULL AND c.archived_at IS NULL
                 AND (l.owner_id = ? OR a.id IS NOT NULL) LIMIT 1""",
            (user_id, customer_id, user_id),
        ).fetchone() is not None

    def _lead_visible(self, lead_id: str, user_id: str) -> bool:
        return self.conn.execute(
            """SELECT 1 FROM leads l
               JOIN customers c ON c.id = l.customer_id
               LEFT JOIN lead_assignments a
                 ON a.lead_id = l.id AND a.user_id = ?
                AND a.assignment_type = 'collaborator' AND a.archived_at IS NULL
               WHERE l.id = ? AND l.archived_at IS NULL AND c.archived_at IS NULL
                 AND (l.owner_id = ? OR a.id IS NOT NULL)""",
            (user_id, lead_id, user_id),
        ).fetchone() is not None

    def _lead_context(self, entity_type: str, entity_id: str) -> tuple[Optional[str], Optional[str]]:
        if entity_type == "leads":
            row = self.conn.execute(
                """SELECT l.id FROM leads l JOIN customers c ON c.id = l.customer_id
                   WHERE l.id = ? AND l.archived_at IS NULL AND c.archived_at IS NULL""",
                (entity_id,),
            ).fetchone()
            return (entity_id, None) if row else (None, None)
        table = {
            "activities": "lead_activities", "assignments": "lead_assignments",
            "pre_sales_tasks": "pre_sales_tasks", "after_sales_tasks": "after_sales_tasks",
        }.get(entity_type)
        if table:
            assignee = "e.assignee_id" if entity_type.endswith("tasks") else "NULL"
            row = self.conn.execute(
                f"""SELECT e.lead_id, {assignee} AS assignee_id
                    FROM {table} e JOIN leads l ON l.id = e.lead_id
                    JOIN customers c ON c.id = l.customer_id
                    WHERE e.id = ? AND e.archived_at IS NULL
                      AND l.archived_at IS NULL AND c.archived_at IS NULL""",
                (entity_id,),
            ).fetchone()
            return (row["lead_id"], row["assignee_id"]) if row else (None, None)
        return None, None

    def _customer_id(self, entity_type: str, entity_id: str) -> Optional[str]:
        if entity_type == "customers":
            row = self.conn.execute(
                "SELECT id FROM customers WHERE id = ? AND archived_at IS NULL", (entity_id,)
            ).fetchone()
            return entity_id if row else None
        table = {"contacts": "customer_contacts", "aliases": "customer_aliases"}.get(entity_type)
        if not table:
            return None
        row = self.conn.execute(
            f"""SELECT e.customer_id FROM {table} e
                JOIN customers c ON c.id = e.customer_id
                WHERE e.id = ? AND e.archived_at IS NULL AND c.archived_at IS NULL""",
            (entity_id,),
        ).fetchone()
        return row["customer_id"] if row else None
