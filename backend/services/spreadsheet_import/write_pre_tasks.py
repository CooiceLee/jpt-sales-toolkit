"""Transactional pre-sales task writer."""

from ...repositories.base import now_iso
from .member_matching import token_for
from .persistence_common import (
    CLEAR, CLEAR_TOKEN, action_for, apply_archive_action, selected_value, upsert,
)
from .persistence_json import merged_field_json
from .related_common import finish_record, local_record, row_version

REQUEST_FIELDS = ("request_description", "request_date", "customer_decision_maker",
                  "quantity_text", "competitor", "key_points", "concerns")
RESULT_FIELDS = ("progress_text", "result_summary", "next_action", "supplemental_notes")


def write_pre_task(conn, canonical, context, actor_id, batch_id, ids, counts, item):
    local_id, existed = local_record(conn, canonical, "pre_sales_tasks", item)
    action = action_for(item)
    if action in {"ARCHIVE", "RESTORE"} and not existed:
        raise ValueError(f"Cannot {action.lower()} unknown pre-sales task {item['external_key']}")
    if not apply_archive_action(conn, "pre_sales_tasks", local_id, action, actor_id):
        _upsert_pre_task(conn, local_id, existed, context, actor_id, ids, item)
    finish_record(
        conn, canonical, "pre_sales_tasks", item, local_id, batch_id, ids, counts, existed
    )


def _upsert_pre_task(conn, local_id, existed, context, actor_id, ids, item):
    token, now = token_for(item, "task_assignee"), now_iso()
    current = conn.execute(
        "SELECT request_json, result_json FROM pre_sales_tasks WHERE id = ?", (local_id,)
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
        values["row_version"] = row_version(conn, "pre_sales_tasks", local_id) + 1
    else:
        values.update({"created_at": now, "created_by": actor_id,
                       "row_version": 1, "archived_at": None})
    upsert(conn, "pre_sales_tasks", local_id, values)


def _status(value, existed):
    if value in (None, ""):
        return None if existed else "Open"
    if value not in {"Open", "In Progress", "Completed", "Cancelled"}:
        raise ValueError(f"Invalid pre-sales task status: {value}")
    return value
