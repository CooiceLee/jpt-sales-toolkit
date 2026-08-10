"""Three-way result merge helpers for Tech task exchange."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime

from ..repositories.base import now_iso
from .tech_task_exchange_contract import (
    AFTER_CHANGE_FIELDS,
    PRE_RESULT_FIELDS,
    parse_object,
    project,
    project_json,
)


class ResultStateMixin:
    """Compare task-result states without mixing in Leader-owned request fields."""

    @staticmethod
    def _parse_snapshot(binding: dict) -> dict:
        return parse_object(binding["source_snapshot_json"])

    def _result_monotonicity_issues(self, package: dict) -> list[dict]:
        latest = self.repo.latest_imported_result(
            package["organization_id"], package["source_user_id"]
        )
        if not latest or latest["package_id"] == package["package_id"]:
            return []
        try:
            incoming_at = datetime.fromisoformat(package["created_at"])
            latest_at = datetime.fromisoformat(latest["created_at"])
            if incoming_at.utcoffset() is None or latest_at.utcoffset() is None:
                raise ValueError("timezone is required")
        except (TypeError, ValueError):
            return [self._issue(
                "error", "invalid_result_timestamp",
                "Tech result package has an invalid creation timestamp",
            )]
        if incoming_at > latest_at:
            return []
        return [self._issue(
            "error", "stale_result_package",
            "Tech result package is not newer than the last imported result package",
        )]

    def _effective_result_baseline(
        self, package: dict, item: dict, assignment_item: dict
    ) -> dict:
        effective = deepcopy(assignment_item)
        task = effective["task"]
        batches = self.repo.imported_result_batches(
            package["organization_id"], package["source_user_id"],
            package["recipient_user_id"],
        )
        for batch in batches:
            manifest = json.loads(batch["manifest_json"])
            for previous in manifest.get("tasks", []):
                if self._same_result_stream(previous, item):
                    self._advance_result_task(item["task_type"], task, previous["changes"])
        return effective

    @staticmethod
    def _same_result_stream(previous: dict, current: dict) -> bool:
        return (
            previous.get("source_package_id") == current["source_package_id"]
            and previous.get("task_type") == current["task_type"]
            and previous.get("source_task_id") == current["source_task_id"]
            and previous.get("source_lead_id") == current["source_lead_id"]
        )

    @staticmethod
    def _advance_result_task(task_type: str, task: dict, changes: dict) -> None:
        if task_type == "pre_sales":
            if "status" in changes:
                task["status"] = changes["status"]
            if "result_json" in changes:
                task["result_json"] = deepcopy(changes["result_json"])
            return
        for key, value in changes.items():
            task[key] = value

    @staticmethod
    def _result_state(task_type: str, source: dict) -> dict:
        if task_type == "pre_sales":
            return {
                "status": source.get("status"),
                "result_json": project_json(source.get("result_json"), PRE_RESULT_FIELDS),
            }
        return project(source, AFTER_CHANGE_FIELDS)

    def _result_changes(self, task_type: str, baseline: dict, current: dict) -> dict:
        before = self._result_state(task_type, baseline)
        after = self._result_state(task_type, current)
        return {key: value for key, value in after.items() if value != before.get(key)}

    def _sync_service_status(self, lead_id: str, actor_id: str) -> None:
        rows = self.conn.execute(
            "SELECT status FROM after_sales_tasks WHERE lead_id = ? AND archived_at IS NULL",
            (lead_id,),
        ).fetchall()
        statuses = {row[0] for row in rows}
        order = ("Open", "In Progress", "Resolved", "Closed")
        service_status = next((value for value in order if value in statuses), "None")
        self.conn.execute(
            """UPDATE leads
               SET service_status = ?, updated_at = ?, updated_by = ?,
                   row_version = row_version + 1
               WHERE id = ? AND archived_at IS NULL AND service_status != ?""",
            (service_status, now_iso(), actor_id, lead_id, service_status),
        )
