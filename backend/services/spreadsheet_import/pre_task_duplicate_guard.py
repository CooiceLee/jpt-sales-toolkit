"""Preflight safety gate for pre-sales tasks collapsed onto one Tech account."""

from __future__ import annotations

import json

from .bindings import binding_id, external_keys

_VALUE_FIELDS = (
    "lead_id", "assignee_id", "client_request_id", "status", "due_date",
)
_JSON_FIELDS = ("request_json", "result_json")
_INVALID = object()


def pre_task_duplicate_issues(conn, dataset_id: str, items: list[dict]) -> list[dict]:
    """Attach safe plans to equivalent duplicates and block every lossy collapse."""
    issues = []
    for item in items:
        rows = _active_bound_rows(conn, dataset_id, item)
        if len(rows) < 2:
            continue
        survivor, duplicates = rows[0], rows[1:]
        fields = sorted({
            field
            for duplicate in duplicates
            for field in _different_fields(survivor, duplicate)
        })
        if any(has_active_task_updates(conn, row["id"]) for row in duplicates):
            fields.append("task_update_history")
        if fields:
            issues.append(_conflict_issue(item, sorted(set(fields))))
            continue
        item["_dedupe_plan"] = {
            "survivor_id": survivor["id"],
            "survivor_row_version": survivor["row_version"],
            "duplicates": [
                {"id": row["id"], "row_version": row["row_version"]}
                for row in duplicates
            ],
        }
    return issues


def has_active_task_updates(conn, task_id: str) -> bool:
    row = conn.execute(
        """SELECT 1 FROM lead_activities
           WHERE archived_at IS NULL AND action_type = 'task_update'
             AND CASE WHEN json_valid(payload_json)
                      THEN json_extract(payload_json, '$.task_id') = ?
                      ELSE 0 END
           LIMIT 1""",
        (task_id,),
    ).fetchone()
    return row is not None


def _active_bound_rows(conn, dataset_id: str, item: dict) -> list:
    ids = list(dict.fromkeys(
        binding_id(conn, dataset_id, "pre_sales_tasks", key)
        for key in external_keys(item)
    ))
    ids = [value for value in ids if value]
    if not ids:
        return []
    marks = ", ".join("?" for _ in ids)
    return conn.execute(
        f"""SELECT id, lead_id, assignee_id, client_request_id, status, due_date,
                   request_json, result_json, created_at, row_version
            FROM pre_sales_tasks
            WHERE id IN ({marks}) AND archived_at IS NULL
            ORDER BY created_at, id""",
        ids,
    ).fetchall()


def _different_fields(left, right) -> set[str]:
    result = {
        field for field in _VALUE_FIELDS
        if left[field] != right[field]
    }
    for field in _JSON_FIELDS:
        left_value, right_value = _json_object(left[field]), _json_object(right[field])
        if _INVALID in (left_value, right_value) or left_value != right_value:
            result.add(field)
    return result


def _json_object(value):
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return _INVALID
    return parsed if isinstance(parsed, dict) else _INVALID


def _conflict_issue(item: dict, fields: list[str]) -> dict:
    ref = item.get("source_ref") or {}
    message = (
        "Existing linked pre-sales tasks differ or contain update history. "
        "Review and archive the duplicate tasks in the App, then run preflight again."
    )
    return {
        "severity": "error",
        "code": "pre_sales_duplicate_conflict",
        "entity_type": "pre_sales_tasks",
        "external_key": item.get("external_key"),
        "field": ",".join(fields),
        "message": message,
        "source_ref": ref,
        "source_record_key": ref.get("record_key"),
    }
