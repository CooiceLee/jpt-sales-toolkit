"""Safe adoption of exact source records on a legacy cloned Tech database."""

from __future__ import annotations

import json

from .tech_task_exchange_contract import (
    AFTER_TASK_FIELDS,
    PRE_REQUEST_FIELDS,
    PRE_RESULT_FIELDS,
    PackageValidationError,
    project,
    project_json,
)


class ExactSourceAdoptionMixin:
    """Reuse exact, aligned source IDs instead of creating duplicate replicas."""

    def _source_adoption_binding(self, item: dict, package: dict) -> dict | None:
        task = self._task(item["task_type"], item["source_task_id"])
        lead = self._row("leads", item["source_lead_id"])
        customer = self._row("customers", item["source_customer_id"])
        records = (task, lead, customer)
        if not any(records):
            return None
        if not all(records):
            raise PackageValidationError(
                "source_identity_collision",
                "Only part of the source task identity already exists locally",
            )
        if any(record.get("archived_at") for record in records):
            raise PackageValidationError(
                "source_identity_collision",
                "An archived source task identity already exists locally",
            )
        aligned = (
            task["lead_id"] == item["source_lead_id"]
            and lead["customer_id"] == item["source_customer_id"]
            and task.get("assignee_id") == package["recipient_user_id"]
        )
        if not aligned:
            raise PackageValidationError(
                "source_identity_collision",
                "Existing source records do not match the package task, lead, customer and Tech assignment",
            )
        if (
            task["row_version"] != item["base_row_version"]
            or self._task_projection(item["task_type"], task) != item["task"]
        ):
            raise PackageValidationError(
                "source_identity_collision",
                "Existing source task is not the exact package baseline",
            )
        return {
            "organization_id": package["organization_id"],
            "task_type": item["task_type"],
            "source_task_id": item["source_task_id"],
            "local_task_id": item["source_task_id"],
            "source_lead_id": item["source_lead_id"],
            "local_lead_id": item["source_lead_id"],
            "source_customer_id": item["source_customer_id"],
            "local_customer_id": item["source_customer_id"],
            "leader_user_id": package["source_user_id"],
            "tech_user_id": package["recipient_user_id"],
            "source_row_version": item["base_row_version"],
            "source_snapshot_json": json.dumps(
                item["task"], ensure_ascii=False, separators=(",", ":")
            ),
            "source_package_id": package["package_id"],
            "local_row_version_at_sync": task["row_version"],
            "last_exported_local_row_version": None,
            "is_active": 1,
        }

    @staticmethod
    def _task_projection(task_type: str, task: dict) -> dict:
        if task_type == "pre_sales":
            return {
                "status": task.get("status"),
                "request_json": project_json(
                    task.get("request_json"), PRE_REQUEST_FIELDS
                ),
                "result_json": project_json(
                    task.get("result_json"), PRE_RESULT_FIELDS
                ),
                "due_date": task.get("due_date"),
            }
        return project(task, AFTER_TASK_FIELDS)
