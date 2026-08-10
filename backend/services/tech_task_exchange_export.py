"""Package export projections for the offline Tech task exchange."""

from __future__ import annotations

from ..repositories.base import generate_uuid
from .lead_extra_fields import parse_extra_json
from .tech_task_exchange_common import TechTaskExchangeError
from .tech_task_exchange_contract import (
    AFTER_TASK_FIELDS,
    ASSIGNMENT_TYPE,
    CUSTOMER_CONTEXT_FIELDS,
    LEADER_TO_TECH,
    LEAD_CONTEXT_FIELDS,
    PACKAGE_VERSION,
    PRE_REQUEST_FIELDS,
    PRE_RESULT_FIELDS,
    RESULT_TYPE,
    TECH_TO_LEADER,
    finalize_package,
    parse_object,
    project,
    project_json,
)


class AssignmentExportMixin:
    """Build minimal Leader assignments and Tech result packages."""

    def export_assignments(self, leader: dict, recipient_user_id: str) -> dict:
        recipient = self._active_user(recipient_user_id, "tech")
        organization_id = self._organization_id(leader["id"])
        if self._organization_id(recipient["id"]) != organization_id:
            raise TechTaskExchangeError(
                "organization_mismatch", "Recipient belongs to another organization", 403
            )
        package = finalize_package({
            "package_type": ASSIGNMENT_TYPE,
            "package_version": PACKAGE_VERSION,
            "package_id": generate_uuid(),
            "direction": LEADER_TO_TECH,
            "organization_id": organization_id,
            "source_user_id": leader["id"],
            "recipient_user_id": recipient["id"],
            "created_at": self._utc_now(),
            "parent_package_id": None,
            "tasks": self._assignment_items(recipient["id"]),
        })
        self._transactional(lambda: self.repo.record_batch(package, "exported"))
        return package

    def export_results(self, tech: dict) -> dict:
        organization_id = self._organization_id(tech["id"])
        bindings = self.repo.list_bindings_for_tech(organization_id, tech["id"])
        items, exported_bindings = [], []
        for binding in bindings:
            current = self._task(binding["task_type"], binding["local_task_id"])
            if not current or current.get("archived_at") or current.get("assignee_id") != tech["id"]:
                continue
            exported_snapshot = binding.get("last_exported_result_snapshot_json")
            baseline = (
                parse_object(exported_snapshot)
                if exported_snapshot is not None
                else self._result_state(
                    binding["task_type"], self._parse_snapshot(binding)
                )
            )
            current_state = self._result_state(binding["task_type"], current)
            if current_state == baseline:
                continue
            items.append({
                "task_type": binding["task_type"],
                "source_task_id": binding["source_task_id"],
                "source_lead_id": binding["source_lead_id"],
                "base_row_version": binding["source_row_version"],
                "source_package_id": binding["source_package_id"],
                # A full permitted result state keeps each package standalone,
                # including an explicit return to the assignment baseline.
                "changes": current_state,
            })
            exported_bindings.append(
                (binding["id"], current["row_version"], current_state)
            )
        leader_ids = {item["leader_user_id"] for item in bindings if item.get("is_active")}
        if len(leader_ids) > 1:
            raise TechTaskExchangeError(
                "multiple_leader_recipients",
                "Pending task results belong to multiple Leaders; export them separately after refreshing assignments",
                409,
            )
        recipient_id = next(iter(leader_ids), None) or self._default_leader_id()
        self._active_user(recipient_id, "leader")
        parent_ids = {item["source_package_id"] for item in items}
        package = finalize_package({
            "package_type": RESULT_TYPE,
            "package_version": PACKAGE_VERSION,
            "package_id": generate_uuid(),
            "direction": TECH_TO_LEADER,
            "organization_id": organization_id,
            "source_user_id": tech["id"],
            "recipient_user_id": recipient_id,
            "created_at": self._utc_now(),
            "parent_package_id": next(iter(parent_ids)) if len(parent_ids) == 1 else None,
            "tasks": items,
        })

        def persist() -> None:
            self.repo.record_batch(package, "exported")
            for binding_id, row_version, result_snapshot in exported_bindings:
                self.repo.mark_exported(binding_id, row_version, result_snapshot)

        self._transactional(persist)
        return package

    def _assignment_items(self, tech_id: str) -> list[dict]:
        rows = []
        for task_type, table in (
            ("pre_sales", "pre_sales_tasks"),
            ("after_sales", "after_sales_tasks"),
        ):
            query = f"""
                SELECT t.*, l.*, t.id AS task_id, t.row_version AS task_row_version,
                       t.status AS task_status, t.created_at AS task_created_at,
                       t.updated_at AS task_updated_at,
                       c.id AS source_customer_id, c.display_name, c.industry,
                       c.customer_type, c.country, c.city, c.region, c.language,
                       c.company_size, c.company_description
                FROM {table} t
                JOIN leads l ON l.id = t.lead_id AND l.archived_at IS NULL
                JOIN customers c ON c.id = l.customer_id AND c.archived_at IS NULL
                WHERE t.assignee_id = ? AND t.archived_at IS NULL
                ORDER BY t.updated_at, t.id
            """
            rows.extend(
                (task_type, dict(row))
                for row in self.conn.execute(query, (tech_id,)).fetchall()
            )
        return [self._assignment_item(task_type, row) for task_type, row in rows]

    @staticmethod
    def _assignment_item(task_type: str, row: dict) -> dict:
        customer = project(row, CUSTOMER_CONTEXT_FIELDS)
        lead = project(row, LEAD_CONTEXT_FIELDS)
        lead.update(project(parse_extra_json(row.get("extra_json")), LEAD_CONTEXT_FIELDS))
        if task_type == "pre_sales":
            task = {
                "status": row["task_status"],
                "request_json": project_json(row.get("request_json"), PRE_REQUEST_FIELDS),
                "result_json": project_json(row.get("result_json"), PRE_RESULT_FIELDS),
                "due_date": row.get("due_date"),
            }
        else:
            task = project(row, AFTER_TASK_FIELDS)
            task["status"] = row["task_status"]
        return {
            "task_type": task_type,
            "source_task_id": row["task_id"],
            "source_lead_id": row["lead_id"],
            "source_customer_id": row["source_customer_id"],
            "base_row_version": int(row["task_row_version"]),
            "customer_context": customer,
            "lead_context": lead,
            "task": task,
        }
