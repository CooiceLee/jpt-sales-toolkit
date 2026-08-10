"""Local Tech task replica creation and refresh."""

from __future__ import annotations

from typing import Optional

from ..repositories.base import generate_uuid, now_iso
from .tech_task_exchange_common import TechTaskExchangeError
from .tech_task_exchange_contract import PRE_RESULT_FIELDS, parse_object


class ReplicaTaskMixin:
    """Upsert task replicas while preserving unsent Tech result fields."""

    def _upsert_local_task(
        self,
        item: dict,
        package: dict,
        actor: dict,
        binding: Optional[dict],
        lead_id: str,
    ) -> tuple[str, bool]:
        current = self._task(item["task_type"], binding["local_task_id"]) if binding else None
        if current and current.get("archived_at"):
            current = None
        if not current:
            return self._insert_local_task(item, package, actor, lead_id), True
        baseline = parse_object(binding["source_snapshot_json"])
        result_state = self._merged_assignment_result(
            item["task_type"], baseline, current, item["task"]
        )
        values = self._assignment_task_values(item["task_type"], item["task"], result_state)
        if item["task_type"] == "pre_sales":
            values["result_json"] = self._preserve_unknown_pre_result_fields(
                current.get("result_json"), values.get("result_json")
            )
        changed = {
            key: value
            for key, value in values.items()
            if self._stored(current.get(key)) != self._stored(value)
        }
        if changed:
            self._update_local_task(item, actor, current, lead_id, changed)
        return current["id"], False

    def _preserve_unknown_pre_result_fields(self, current, incoming):
        """Keep legacy local result keys that are outside the exchange whitelist."""
        merged = {
            key: value
            for key, value in parse_object(current).items()
            if key not in PRE_RESULT_FIELDS
        }
        merged.update(parse_object(incoming))
        return self._json(merged)

    def _insert_local_task(
        self, item: dict, package: dict, actor: dict, lead_id: str
    ) -> str:
        task_id, task, timestamp = generate_uuid(), item["task"], now_iso()
        if item["task_type"] == "pre_sales":
            self.conn.execute(
                """INSERT INTO pre_sales_tasks (
                    id, lead_id, assignee_id, status, request_json, result_json, due_date,
                    created_at, created_by, updated_at, updated_by, row_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    task_id, lead_id, actor["id"], task["status"],
                    self._json(task.get("request_json")), self._json(task.get("result_json")),
                    task.get("due_date"), timestamp, package["source_user_id"],
                    timestamp, actor["id"],
                ),
            )
        else:
            self.conn.execute(
                """INSERT INTO after_sales_tasks (
                    id, lead_id, assignee_id, issue_type, status, issue_description,
                    solution, customer_satisfaction, lessons_learned, remarks, due_date,
                    created_at, created_by, updated_at, updated_by, row_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    task_id, lead_id, actor["id"], task["issue_type"], task["status"],
                    task["issue_description"], task.get("solution"),
                    task.get("customer_satisfaction"), task.get("lessons_learned"),
                    task.get("remarks"), task.get("due_date"), timestamp,
                    package["source_user_id"], timestamp, actor["id"],
                ),
            )
        return task_id

    def _update_local_task(
        self, item: dict, actor: dict, current: dict, lead_id: str, changed: dict
    ) -> None:
        assignments = ", ".join(f"{key} = ?" for key in changed)
        cursor = self.conn.execute(
            f"""UPDATE {self._task_table(item['task_type'])}
                SET {assignments}, lead_id = ?, assignee_id = ?,
                    updated_at = ?, updated_by = ?, row_version = row_version + 1
                WHERE id = ? AND row_version = ? AND archived_at IS NULL""",
            (
                *changed.values(), lead_id, actor["id"], now_iso(), actor["id"],
                current["id"], current["row_version"],
            ),
        )
        if cursor.rowcount != 1:
            raise TechTaskExchangeError(
                "local_task_changed", "Local Tech task changed during import", 409
            )
