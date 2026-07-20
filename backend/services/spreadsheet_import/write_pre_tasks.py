"""Transactional pre-sales task writer."""

from ...repositories.base import now_iso
from .bindings import external_keys
from .member_matching import token_for
from .errors import SpreadsheetImportError
from .persistence_common import (
    CLEAR, CLEAR_TOKEN, action_for, apply_archive_action, selected_value, upsert,
)
from .persistence_json import merged_field_json
from .pre_task_duplicate_apply import (
    archive_planned_duplicates, resolve_pre_task_record,
)
from .related_common import finish_record

REQUEST_FIELDS = ("request_description", "request_date", "request_date_raw",
                  "due_date_raw", "customer_decision_maker", "quantity_text",
                  "competitor", "key_points", "concerns")
RESULT_FIELDS = ("progress_text", "result_summary", "next_action", "supplemental_notes")


def write_pre_task(conn, canonical, context, actor_id, batch_id, ids, counts, item):
    local_id, existed, duplicates, expected_version = resolve_pre_task_record(
        conn, canonical, item
    )
    action = action_for(item)
    if action in {"ARCHIVE", "RESTORE"} and not existed:
        raise ValueError(f"Cannot {action.lower()} unknown pre-sales task {item['external_key']}")
    handled_lifecycle = apply_archive_action(
        conn, "pre_sales_tasks", local_id, action, actor_id
    )
    if not handled_lifecycle:
        _upsert_pre_task(
            conn, local_id, existed, context, actor_id, ids, item, expected_version
        )
    archive_planned_duplicates(
        conn, duplicates, local_id, actor_id, external_keys(item)
    )
    finish_record(
        conn, canonical, "pre_sales_tasks", item, local_id, batch_id, ids, counts, existed
    )


def _upsert_pre_task(
    conn, local_id, existed, context, actor_id, ids, item, expected_version=None,
):
    token, now = token_for(item, "task_assignee"), now_iso()
    current = conn.execute(
        """SELECT request_json, result_json, row_version, archived_at
           FROM pre_sales_tasks WHERE id = ?""",
        (local_id,),
    ).fetchone()
    values = {
        "lead_id": ids["leads"][item["lead_key"]],
        "assignee_id": (CLEAR if token == CLEAR_TOKEN else
                        context["member_ids"].get((token, "task_assignee")) if token else None),
        "status": _status(item.get("status"), existed),
        "due_date": selected_value(item, "due_date"),
        "request_json": merged_field_json(current[0] if current else None, item, REQUEST_FIELDS),
        "result_json": merged_field_json(current[1] if current else None, item, RESULT_FIELDS),
        "updated_at": now, "updated_by": actor_id,
    }
    if existed:
        current_version = current["row_version"]
        values["row_version"] = current_version + 1
    else:
        values.update({"created_at": now, "created_by": actor_id,
                       "row_version": 1, "archived_at": None})
    if expected_version is None:
        upsert(conn, "pre_sales_tasks", local_id, values)
        return
    if current_version != expected_version or current["archived_at"] is not None:
        raise _changed_error()
    clean = {
        key: (None if value is CLEAR else value)
        for key, value in values.items() if value is not None
    }
    assignments = ", ".join(f"{key} = ?" for key in clean)
    cursor = conn.execute(
        f"""UPDATE pre_sales_tasks SET {assignments}
            WHERE id = ? AND row_version = ? AND archived_at IS NULL""",
        (*clean.values(), local_id, expected_version),
    )
    if cursor.rowcount != 1:
        raise _changed_error()


def _changed_error() -> SpreadsheetImportError:
    return SpreadsheetImportError(
        "pre_sales_duplicate_changed",
        "Pre-sales task data changed after preflight; run preflight again",
        409,
    )


def _status(value, existed):
    if value in (None, ""):
        return None if existed else "Open"
    if value not in {"Open", "In Progress", "Completed", "Cancelled"}:
        raise ValueError(f"Invalid pre-sales task status: {value}")
    return value
