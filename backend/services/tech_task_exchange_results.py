"""Leader-side validation and merge of Tech task results."""

from __future__ import annotations

import json

from ..repositories.activity_repository import ActivityRepository
from ..repositories.audit_repository import AuditRepository
from ..repositories.base import now_iso
from .tech_task_exchange_common import TechTaskExchangeError
from .tech_task_exchange_contract import (
    ASSIGNMENT_TYPE,
    PackageValidationError,
    validate_result_item,
)


class ResultMergeMixin:
    """Analyze and atomically apply a Tech-to-Leader result package."""

    def _result_analysis(self, package: dict) -> tuple[list[dict], list[dict]]:
        issues = self._result_monotonicity_issues(package)
        plans, seen = [], set()
        for raw in package.get("tasks") or []:
            label = raw.get("source_task_id") if isinstance(raw, dict) else None
            try:
                item = validate_result_item(raw)
                key = (item["task_type"], item["source_task_id"])
                if key in seen:
                    raise PackageValidationError(
                        "duplicate_task", "Task appears more than once in package"
                    )
                seen.add(key)
                baseline_item = self._result_baseline(package, item)
                current = self._task(item["task_type"], item["source_task_id"])
                if not current or current.get("archived_at"):
                    raise PackageValidationError(
                        "source_task_unavailable", "Source task is missing or archived"
                    )
                if current.get("assignee_id") != package["source_user_id"]:
                    raise PackageValidationError(
                        "task_reassigned", "Source task was reassigned to another technician"
                    )
                conflicts = self._result_conflicts(
                    item["task_type"], baseline_item["task"], current, item["changes"]
                )
                if conflicts:
                    issues.append(self._issue(
                        "conflict",
                        "source_task_changed",
                        "Leader and Tech changed the same fields: " + ", ".join(conflicts),
                        label,
                    ))
                    continue
                plans.append({
                    "item": item,
                    "current": current,
                    "baseline": baseline_item["task"],
                })
            except (PackageValidationError, json.JSONDecodeError) as error:
                issues.append(self._issue(
                    "error",
                    getattr(error, "code", "invalid_assignment_manifest"),
                    str(error),
                    label,
                ))
        return issues, plans

    def _result_baseline(self, package: dict, item: dict) -> dict:
        source_batch = self.repo.get_batch(item["source_package_id"])
        if not source_batch or source_batch["status"] != "exported":
            raise PackageValidationError(
                "unknown_assignment_package", "Original Leader assignment package was not found"
            )
        if (
            source_batch["package_type"] != ASSIGNMENT_TYPE
            or source_batch["source_user_id"] != package["recipient_user_id"]
            or source_batch["recipient_user_id"] != package["source_user_id"]
            or source_batch["organization_id"] != package["organization_id"]
        ):
            raise PackageValidationError(
                "assignment_identity_mismatch",
                "Original assignment package identity does not match",
            )
        manifest = json.loads(source_batch["manifest_json"])
        baseline = next(
            (
                candidate
                for candidate in manifest.get("tasks", [])
                if candidate.get("task_type") == item["task_type"]
                and candidate.get("source_task_id") == item["source_task_id"]
            ),
            None,
        )
        if not baseline:
            raise PackageValidationError(
                "task_not_in_assignment", "Task was not included in the original assignment package"
            )
        if (
            item["base_row_version"] != baseline.get("base_row_version")
            or item["source_lead_id"] != baseline.get("source_lead_id")
        ):
            raise PackageValidationError(
                "task_baseline_mismatch", "Task baseline does not match the original assignment"
            )
        return self._effective_result_baseline(package, item, baseline)

    def _apply_results(self, package: dict, actor: dict, plans: list[dict]) -> dict:
        updated = unchanged = 0
        affected_after_leads = set()
        for plan in plans:
            item = plan["item"]
            current = self._task(item["task_type"], item["source_task_id"])
            values = self._result_update_values(
                item["task_type"], plan["baseline"], current, item["changes"]
            )
            if not values:
                unchanged += 1
                continue
            self._update_source_task(package, actor, item, current, values)
            if item["task_type"] == "after_sales":
                affected_after_leads.add(current["lead_id"])
            updated += 1
        for lead_id in affected_after_leads:
            self._sync_service_status(lead_id, actor["id"])
        return {"imported": updated, "updated": updated, "unchanged": unchanged}

    def _update_source_task(
        self, package: dict, actor: dict, item: dict, current: dict, values: dict
    ) -> None:
        assignments = ", ".join(f"{key} = ?" for key in values)
        cursor = self.conn.execute(
            f"""UPDATE {self._task_table(item['task_type'])}
                SET {assignments}, updated_at = ?, updated_by = ?, row_version = row_version + 1
                WHERE id = ? AND row_version = ? AND archived_at IS NULL
                  AND assignee_id = ?""",
            (
                *values.values(), now_iso(), actor["id"], item["source_task_id"],
                current["row_version"], package["source_user_id"],
            ),
        )
        if cursor.rowcount != 1:
            raise TechTaskExchangeError(
                "task_changed_after_preflight",
                "Task changed while the result package was being imported",
                409,
            )
        AuditRepository(self.conn).log(
            item["task_type"] + "_task",
            item["source_task_id"],
            "tech_package_result_import",
            actor["id"],
            before_json=json.dumps(
                {key: current.get(key) for key in values}, ensure_ascii=False
            ),
            after_json=json.dumps(
                {"source_tech_id": package["source_user_id"], "changes": values},
                ensure_ascii=False,
            ),
            commit=False,
        )
        ActivityRepository(self.conn).create(
            current["lead_id"],
            actor["id"],
            "task_update",
            "Technical task result imported",
            payload_json=json.dumps({
                "task_type": item["task_type"],
                "task_id": item["source_task_id"],
                "source_tech_id": package["source_user_id"],
                "package_id": package["package_id"],
            }),
            visibility="internal",
            commit=False,
        )
