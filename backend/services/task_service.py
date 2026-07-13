"""
Task services - pre-sales and after-sales task management.
"""

from __future__ import annotations

import json
from typing import Optional

from ..repositories import (
    PreSalesTaskRepository,
    AfterSalesTaskRepository,
    ActivityRepository,
    AuditRepository,
    LeadRepository,
)
from ..repositories.base import ConflictError, now_iso


class PreSalesTaskService:
    """Pre-sales task management service."""

    def __init__(
        self,
        task_repo: Optional[PreSalesTaskRepository] = None,
        activity_repo: Optional[ActivityRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
    ):
        self.task_repo = task_repo or PreSalesTaskRepository()
        self.activity_repo = activity_repo or ActivityRepository()
        self.audit_repo = audit_repo or AuditRepository()

    def create(self, lead_id: str, data: dict, actor_id: str) -> dict:
        """Create new pre-sales task."""
        task_id = self.task_repo.create(lead_id, data, actor_id)

        # Log audit
        self.audit_repo.log(
            entity_type="pre_sales_task",
            entity_id=task_id,
            event_type="create",
            actor_id=actor_id,
            after_json=json.dumps(data),
        )

        # Create activity on lead
        self.activity_repo.create(
            lead_id=lead_id,
            actor_id=actor_id,
            action_type="task_update",
            summary="Pre-sales task created",
            payload_json=json.dumps({
                "task_type": "pre_sales",
                "task_id": task_id,
                "status": data.get("status", "Open"),
            }),
        )

        return self.task_repo.get_by_id(task_id)

    def update(
        self,
        task_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
    ) -> dict:
        """Update task with conflict detection."""
        before = self.task_repo.get_by_id(task_id)
        if not before:
            raise ValueError(f"PreSalesTask {task_id} not found")

        try:
            updated = self.task_repo.update(task_id, data, actor_id, row_version)

            # Log audit
            self.audit_repo.log(
                entity_type="pre_sales_task",
                entity_id=task_id,
                event_type="update",
                actor_id=actor_id,
                before_json=json.dumps(dict(before)),
                after_json=json.dumps(data),
            )

            # Create activity on lead
            self.activity_repo.create(
                lead_id=before["lead_id"],
                actor_id=actor_id,
                action_type="task_update",
                summary=f"Pre-sales task updated: {data.get('status', '')}",
                payload_json=json.dumps({
                    "task_type": "pre_sales",
                    "task_id": task_id,
                    "status": updated.get("status"),
                }),
            )

            return updated

        except ConflictError:
            raise

    def list(self, actor: dict, filters: Optional[dict] = None) -> list[dict]:
        """List pre-sales tasks with filters."""
        scoped = dict(filters or {})
        if actor["role"] == "tech":
            scoped["assignee_id"] = actor["id"]
        elif actor["role"] != "leader":
            scoped["visible_to_user_id"] = actor["id"]
        return self.task_repo.list(scoped)

    def list_for_lead(self, lead_id: str) -> list[dict]:
        """Get all tasks for a lead."""
        return self.task_repo.list_for_lead(lead_id)

    def archive(self, task_id: str, actor_id: str) -> bool:
        """Archive pre-sales task and related task-update activities."""
        task = self.task_repo.get_by_id(task_id)
        if not task:
            return False
        success = self.task_repo.archive(task_id, actor_id)
        if success:
            self.activity_repo.archive_task_updates(task_id, "pre_sales")
            self.audit_repo.log(
                entity_type="pre_sales_task",
                entity_id=task_id,
                event_type="archive",
                actor_id=actor_id,
                before_json=json.dumps(dict(task)),
            )
        return success

    def restore(self, task_id: str, actor_id: str) -> bool:
        """Restore archived pre-sales task and related activities."""
        task = self.task_repo.get_by_id(task_id)
        if not task:
            return False
        success = self.task_repo.restore(task_id, actor_id)
        if success:
            self.activity_repo.restore_task_updates(task_id, "pre_sales")
            self.audit_repo.log(
                entity_type="pre_sales_task",
                entity_id=task_id,
                event_type="restore",
                actor_id=actor_id,
                after_json=json.dumps(dict(task)),
            )
        return success


class AfterSalesTaskService:
    """After-sales task management service."""

    def __init__(
        self,
        task_repo: Optional[AfterSalesTaskRepository] = None,
        activity_repo: Optional[ActivityRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        lead_repo: Optional[LeadRepository] = None,
    ):
        self.task_repo = task_repo or AfterSalesTaskRepository()
        self.activity_repo = activity_repo or ActivityRepository()
        self.audit_repo = audit_repo or AuditRepository()
        self.lead_repo = lead_repo or LeadRepository()

    def _derive_service_status(self, lead_id: str) -> str:
        """Derive lead service_status from active after-sales tasks."""
        tasks = self.task_repo.list_for_lead(lead_id)
        statuses = {task.get("status") for task in tasks}
        if not statuses:
            return "None"
        if "Open" in statuses:
            return "Open"
        if "In Progress" in statuses:
            return "In Progress"
        if "Resolved" in statuses:
            return "Resolved"
        if "Closed" in statuses:
            return "Closed"
        return "None"

    def _sync_lead_service_status(self, lead_id: str, actor_id: str) -> None:
        """Update the parent lead service_status from active after-sales tasks."""
        service_status = self._derive_service_status(lead_id)
        self.lead_repo.conn.execute(
            """
            UPDATE leads
            SET service_status = ?, updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE id = ? AND archived_at IS NULL AND service_status != ?
            """,
            (service_status, now_iso(), actor_id, lead_id, service_status),
        )
        self.lead_repo.conn.commit()

    def create(self, lead_id: str, data: dict, actor_id: str) -> dict:
        """Create new after-sales task."""
        task_id = self.task_repo.create(lead_id, data, actor_id)
        self._sync_lead_service_status(lead_id, actor_id)

        # Log audit
        self.audit_repo.log(
            entity_type="after_sales_task",
            entity_id=task_id,
            event_type="create",
            actor_id=actor_id,
            after_json=json.dumps(data),
        )

        # Create activity on lead
        self.activity_repo.create(
            lead_id=lead_id,
            actor_id=actor_id,
            action_type="task_update",
            summary=f"After-sales issue: {data.get('issue_type', 'Other')}",
            payload_json=json.dumps({
                "task_type": "after_sales",
                "task_id": task_id,
                "status": data.get("status", "Open"),
            }),
        )

        return self.task_repo.get_by_id(task_id)

    def update(
        self,
        task_id: str,
        data: dict,
        actor_id: str,
        row_version: int,
    ) -> dict:
        """Update task with conflict detection."""
        before = self.task_repo.get_by_id(task_id)
        if not before:
            raise ValueError(f"AfterSalesTask {task_id} not found")

        try:
            updated = self.task_repo.update(task_id, data, actor_id, row_version)
            self._sync_lead_service_status(before["lead_id"], actor_id)

            # Log audit
            self.audit_repo.log(
                entity_type="after_sales_task",
                entity_id=task_id,
                event_type="update",
                actor_id=actor_id,
                before_json=json.dumps(dict(before)),
                after_json=json.dumps(data),
            )

            # Create activity on lead
            self.activity_repo.create(
                lead_id=before["lead_id"],
                actor_id=actor_id,
                action_type="task_update",
                summary=f"After-sales task: {updated.get('status')}",
                payload_json=json.dumps({
                    "task_type": "after_sales",
                    "task_id": task_id,
                    "status": updated.get("status"),
                }),
            )

            return updated

        except ConflictError:
            raise

    def list(self, actor: dict, filters: Optional[dict] = None) -> list[dict]:
        """List after-sales tasks with filters."""
        scoped = dict(filters or {})
        if actor["role"] == "tech":
            scoped["assignee_id"] = actor["id"]
        elif actor["role"] != "leader":
            scoped["visible_to_user_id"] = actor["id"]
        return self.task_repo.list(scoped)

    def list_for_lead(self, lead_id: str) -> list[dict]:
        """Get all tasks for a lead."""
        return self.task_repo.list_for_lead(lead_id)

    def archive(self, task_id: str, actor_id: str) -> bool:
        """Archive after-sales task and related task-update activities."""
        task = self.task_repo.get_by_id(task_id)
        if not task:
            return False

        success = self.task_repo.archive(task_id, actor_id)
        if success:
            self._sync_lead_service_status(task["lead_id"], actor_id)
            self.activity_repo.archive_task_updates(task_id, "after_sales")
            self.audit_repo.log(
                entity_type="after_sales_task",
                entity_id=task_id,
                event_type="archive",
                actor_id=actor_id,
                before_json=json.dumps(dict(task)),
            )
        return success

    def restore(self, task_id: str, actor_id: str) -> bool:
        """Restore archived after-sales task and related task-update activities."""
        task = self.task_repo.get_by_id(task_id)
        if not task:
            return False

        success = self.task_repo.restore(task_id, actor_id)
        if success:
            self._sync_lead_service_status(task["lead_id"], actor_id)
            self.activity_repo.restore_task_updates(task_id, "after_sales")
            self.audit_repo.log(
                entity_type="after_sales_task",
                entity_id=task_id,
                event_type="restore",
                actor_id=actor_id,
                after_json=json.dumps(dict(task)),
            )
        return success
