"""Complete-snapshot withdrawal handling for Tech task assignments."""

from __future__ import annotations

import json
from datetime import datetime

from ..repositories.audit_repository import AuditRepository
from ..repositories.base import now_iso
from .tech_task_exchange_contract import PackageValidationError, parse_object


class AssignmentSnapshotMixin:
    def _snapshot_monotonicity_issues(self, package: dict) -> list[dict]:
        latest = self.repo.latest_imported_assignment(
            package["organization_id"], package["recipient_user_id"],
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
                "error", "invalid_snapshot_timestamp",
                "Assignment snapshot has an invalid creation timestamp",
            )]
        if incoming_at > latest_at:
            return []
        return [self._issue(
            "error", "stale_assignment_snapshot",
            "Assignment snapshot is not newer than the last imported complete snapshot",
        )]

    @staticmethod
    def _binding_key(binding: dict) -> tuple[str, str]:
        return binding["task_type"], binding["source_task_id"]

    def _snapshot_bindings(self, package: dict) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM tech_task_exchange_bindings
               WHERE organization_id = ? AND tech_user_id = ? AND is_active = 1""",
            (
                package["organization_id"], package["recipient_user_id"],
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def _withdrawal_issues(
        self, package: dict, incoming: set[tuple[str, str]]
    ) -> list[dict]:
        issues = []
        for binding in self._snapshot_bindings(package):
            if self._binding_key(binding) in incoming:
                continue
            current = self._task(binding["task_type"], binding["local_task_id"])
            if current and not current.get("archived_at"):
                try:
                    self._assert_binding_identity(package, binding, current)
                except PackageValidationError as error:
                    issues.append(self._issue(
                        "error", error.code, str(error), binding["source_task_id"]
                    ))
                    continue
                if self._has_unexported_result_changes(binding, current):
                    issues.append(self._issue(
                        "conflict", "withdrawal_has_unsent_changes",
                        "Assignment was withdrawn while the Tech copy has unreturned result changes",
                        binding["source_task_id"],
                    ))
                    continue
            issues.append(self._issue(
                "warning", "assignment_withdrawn",
                "Assignment is absent from the latest Leader snapshot and will be archived",
                binding["source_task_id"],
            ))
        return issues

    def _has_unexported_result_changes(
        self, binding: dict, current: dict
    ) -> bool:
        task_type = binding["task_type"]
        current_state = self._result_state(task_type, current)
        source_state = self._result_state(
            task_type, self._parse_snapshot(binding)
        )
        exported_raw = binding.get("last_exported_result_snapshot_json")
        if exported_raw is None:
            return current_state != source_state
        exported_state = parse_object(exported_raw)
        if current_state == exported_state:
            return False
        return not (
            current_state == source_state
            and current["row_version"] == binding["local_row_version_at_sync"]
        )

    def _reconcile_assignment_snapshot(self, package: dict, actor: dict) -> None:
        incoming = {
            (item["task_type"], item["source_task_id"]) for item in package["tasks"]
        }
        for binding in self._snapshot_bindings(package):
            if self._binding_key(binding) not in incoming:
                self._withdraw_binding(binding, package, actor)

    def _withdraw_binding(self, binding: dict, package: dict, actor: dict) -> None:
        timestamp = now_iso()
        self.conn.execute(
            "UPDATE tech_task_exchange_bindings SET is_active = 0, updated_at = ? WHERE id = ?",
            (timestamp, binding["id"]),
        )
        other = self.conn.execute(
            """SELECT 1 FROM tech_task_exchange_bindings
               WHERE id != ? AND task_type = ? AND local_task_id = ? AND is_active = 1
               LIMIT 1""",
            (binding["id"], binding["task_type"], binding["local_task_id"]),
        ).fetchone()
        if not other:
            self.conn.execute(
                f"""UPDATE {self._task_table(binding['task_type'])}
                    SET archived_at = ?, updated_at = ?, updated_by = ?,
                        row_version = row_version + 1
                    WHERE id = ? AND archived_at IS NULL""",
                (timestamp, timestamp, actor["id"], binding["local_task_id"]),
            )
        AuditRepository(self.conn).log(
            binding["task_type"] + "_task", binding["local_task_id"],
            "tech_package_assignment_withdrawn", actor["id"],
            after_json=json.dumps({
                "package_id": package["package_id"],
                "source_task_id": binding["source_task_id"],
                "local_task_archived": not bool(other),
            }),
            commit=False,
        )
