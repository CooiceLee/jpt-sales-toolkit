"""Tech-side validation and application of Leader assignment snapshots."""

from __future__ import annotations

import json

from ..repositories.audit_repository import AuditRepository
from .tech_task_exchange_contract import PackageValidationError, validate_assignment_item


class AssignmentSyncMixin:
    """Apply the latest complete active-assignment snapshot for one Tech."""

    def _assignment_issues(self, package: dict) -> list[dict]:
        issues, seen = self._snapshot_monotonicity_issues(package), set()
        for raw in package.get("tasks") or []:
            label = raw.get("source_task_id") if isinstance(raw, dict) else None
            try:
                item = validate_assignment_item(raw)
                key = (item["task_type"], item["source_task_id"])
                if key in seen:
                    raise PackageValidationError(
                        "duplicate_task", "Task appears more than once in package"
                    )
                seen.add(key)
                binding = self.repo.get_binding(
                    package["organization_id"], item["task_type"],
                    item["source_task_id"], package["recipient_user_id"],
                )
                if not binding:
                    binding = self._source_adoption_binding(item, package)
                    if binding:
                        issues.append(self._issue(
                            "warning", "existing_source_records_adopted",
                            "Matching legacy source records will be adopted without duplication",
                            label,
                        ))
                if binding:
                    self._check_local_binding(package, binding, item, issues)
            except PackageValidationError as error:
                issues.append(self._issue("error", error.code, str(error), label))
        issues.extend(self._withdrawal_issues(package, seen))
        return issues

    def _check_local_binding(
        self, package: dict, binding: dict, item: dict, issues: list[dict]
    ) -> None:
        if item["base_row_version"] < binding["source_row_version"]:
            raise PackageValidationError(
                "stale_task_baseline",
                "Task assignment is older than the last imported task baseline",
            )
        current = self._task(item["task_type"], binding["local_task_id"])
        label = item["source_task_id"]
        if not current or (current.get("archived_at") and binding.get("is_active")):
            raise PackageValidationError(
                "local_task_unavailable", "Previously imported task is unavailable"
            )
        if current and not current.get("archived_at"):
            self._assert_binding_identity(package, binding, current)
        if not binding.get("is_active") or not current or current.get("archived_at"):
            return
        conflict = self._assignment_conflict(
            item["task_type"], binding, current, item["task"]
        )
        if conflict:
            issues.append(self._issue(
                "conflict", "unsent_tech_changes", conflict, label
            ))

    @staticmethod
    def _assert_binding_identity(package: dict, binding: dict, current: dict) -> None:
        if current.get("assignee_id") != package["recipient_user_id"]:
            raise PackageValidationError(
                "local_task_assignee_mismatch",
                "Local task assignee no longer matches the package recipient",
            )
        if current.get("lead_id") != binding.get("local_lead_id"):
            raise PackageValidationError(
                "local_task_lead_mismatch",
                "Local task lead no longer matches its exchange binding",
            )

    def _apply_assignments(self, package: dict, actor: dict) -> dict:
        created = updated = 0
        for item in package["tasks"]:
            binding = self.repo.get_binding(
                package["organization_id"], item["task_type"],
                item["source_task_id"], actor["id"],
            )
            if not binding:
                binding = self._source_adoption_binding(item, package)
            customer_id, lead_id = self._ensure_replica_context(
                item, package, actor, binding
            )
            local_task_id, was_created = self._upsert_local_task(
                item, package, actor, binding, lead_id
            )
            current = self._task(item["task_type"], local_task_id)
            self._save_binding(package, actor, item, current, customer_id, lead_id)
            self._audit_assignment(package, actor, item, local_task_id)
            created += int(was_created)
            updated += int(not was_created)
        self._reconcile_assignment_snapshot(package, actor)
        return {"imported": created, "updated": updated}

    def _save_binding(
        self, package: dict, actor: dict, item: dict, current: dict,
        customer_id: str, lead_id: str,
    ) -> None:
        self.repo.upsert_binding({
            "organization_id": package["organization_id"],
            "task_type": item["task_type"],
            "source_task_id": item["source_task_id"],
            "local_task_id": current["id"],
            "source_lead_id": item["source_lead_id"],
            "local_lead_id": lead_id,
            "source_customer_id": item["source_customer_id"],
            "local_customer_id": customer_id,
            "leader_user_id": package["source_user_id"],
            "tech_user_id": actor["id"],
            "source_row_version": item["base_row_version"],
            "source_snapshot_json": json.dumps(
                item["task"], ensure_ascii=False, separators=(",", ":")
            ),
            "source_package_id": package["package_id"],
            "local_row_version_at_sync": current["row_version"],
        })

    def _audit_assignment(
        self, package: dict, actor: dict, item: dict, local_task_id: str
    ) -> None:
        AuditRepository(self.conn).log(
            item["task_type"] + "_task", local_task_id,
            "tech_package_assignment_import", actor["id"],
            after_json=json.dumps({
                "package_id": package["package_id"],
                "source_task_id": item["source_task_id"],
            }),
            commit=False,
        )
