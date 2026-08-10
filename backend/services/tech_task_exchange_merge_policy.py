"""Field-level three-way merge policy for Tech task results."""

from __future__ import annotations

from .tech_task_exchange_contract import AFTER_TASK_FIELDS, PRE_RESULT_FIELDS
from .tech_task_exchange_contract import parse_object, project


class ResultMergePolicyMixin:
    def _assignment_conflict(
        self, task_type: str, binding: dict, current: dict, incoming: dict
    ) -> str | None:
        old = self._result_state(task_type, self._parse_snapshot(binding))
        local = self._result_state(task_type, current)
        new = self._result_state(task_type, incoming)
        conflicts = self._result_state_conflicts(task_type, old, local, new)
        if not conflicts:
            return None
        return (
            "Local unsent result conflicts with refreshed Leader fields: "
            + ", ".join(conflicts)
        )

    def _merged_assignment_result(
        self, task_type: str, baseline: dict, current: dict, incoming: dict
    ) -> dict:
        old = self._result_state(task_type, baseline)
        local = self._result_state(task_type, current)
        new = self._result_state(task_type, incoming)
        if task_type == "pre_sales":
            return {
                "status": local["status"]
                if local["status"] != old.get("status")
                else new.get("status"),
                "result_json": self._merge_pre_result_objects(
                    old.get("result_json", {}),
                    local.get("result_json", {}),
                    new.get("result_json", {}),
                ),
            }
        return {
            key: local[key] if local[key] != old.get(key) else new.get(key)
            for key in new
        }

    def _assignment_task_values(
        self, task_type: str, incoming: dict, result_state: dict
    ) -> dict:
        if task_type == "pre_sales":
            return {
                "status": result_state["status"],
                "request_json": self._json(incoming.get("request_json")),
                "result_json": self._json(result_state.get("result_json")),
                "due_date": incoming.get("due_date"),
            }
        values = project(incoming, AFTER_TASK_FIELDS)
        values.update(result_state)
        return values

    def _result_conflicts(
        self, task_type: str, baseline: dict, current: dict, changes: dict
    ) -> list[str]:
        old = self._result_state(task_type, baseline)
        live = self._result_state(task_type, current)
        if task_type == "pre_sales":
            requested = dict(live)
            requested.update({
                key: value
                for key, value in changes.items()
                if key != "result_json"
            })
            if "result_json" in changes:
                requested["result_json"] = changes["result_json"]
            return self._result_state_conflicts(
                task_type, old, live, requested, set(changes)
            )
        return [
            key
            for key, requested in changes.items()
            if live.get(key) != old.get(key)
            and requested != old.get(key)
            and requested != live.get(key)
        ]

    @staticmethod
    def _merge_pre_result_objects(old: dict, local: dict, new: dict) -> dict:
        missing = object()
        merged = {}
        for key in PRE_RESULT_FIELDS:
            old_value = old.get(key, missing)
            local_value = local.get(key, missing)
            new_value = new.get(key, missing)
            selected = local_value if local_value != old_value else new_value
            if selected is not missing:
                merged[key] = selected
        return merged

    @staticmethod
    def _result_state_conflicts(
        task_type: str,
        old: dict,
        local: dict,
        new: dict,
        changed_fields: set[str] | None = None,
    ) -> list[str]:
        fields = changed_fields or set(new)
        conflicts = []
        if "status" in fields and (
            local.get("status") != old.get("status")
            and new.get("status") != old.get("status")
            and local.get("status") != new.get("status")
        ):
            conflicts.append("status")
        if task_type != "pre_sales":
            conflicts.extend(
                key
                for key in fields - {"status"}
                if local.get(key) != old.get(key)
                and new.get(key) != old.get(key)
                and local.get(key) != new.get(key)
            )
            return conflicts
        if "result_json" not in fields:
            return conflicts
        missing = object()
        for key in PRE_RESULT_FIELDS:
            old_value = old.get("result_json", {}).get(key, missing)
            local_value = local.get("result_json", {}).get(key, missing)
            new_value = new.get("result_json", {}).get(key, missing)
            if (
                local_value != old_value
                and new_value != old_value
                and local_value != new_value
            ):
                conflicts.append(f"result_json.{key}")
        return conflicts

    def _result_update_values(
        self, task_type: str, baseline: dict, current: dict, requested: dict
    ) -> dict:
        old = self._result_state(task_type, baseline)
        live = self._result_state(task_type, current)
        if task_type != "pre_sales":
            merged = {
                key: live.get(key)
                if live.get(key) != old.get(key) and value == old.get(key)
                else value
                for key, value in requested.items()
            }
            return {
                key: value
                for key, value in merged.items()
                if current.get(key) != value
            }
        values = {}
        if "status" in requested:
            status = (
                live.get("status")
                if live.get("status") != old.get("status")
                and requested["status"] == old.get("status")
                else requested["status"]
            )
            if status != current.get("status"):
                values["status"] = status
        if "result_json" not in requested:
            return values
        merged_result = self._merge_requested_pre_results(
            old.get("result_json", {}),
            live.get("result_json", {}),
            requested["result_json"],
        )
        stored = parse_object(current.get("result_json"))
        for key in PRE_RESULT_FIELDS:
            if key in merged_result:
                stored[key] = merged_result[key]
            else:
                stored.pop(key, None)
        encoded = self._json(stored)
        if self._stored(encoded) != self._stored(current.get("result_json")):
            values["result_json"] = encoded
        return values

    @staticmethod
    def _merge_requested_pre_results(
        old: dict, live: dict, requested: dict
    ) -> dict:
        missing = object()
        merged = {}
        for key in PRE_RESULT_FIELDS:
            old_value = old.get(key, missing)
            live_value = live.get(key, missing)
            requested_value = requested.get(key, missing)
            selected = (
                live_value
                if live_value != old_value and requested_value == old_value
                else requested_value
            )
            if selected is not missing:
                merged[key] = selected
        return merged
