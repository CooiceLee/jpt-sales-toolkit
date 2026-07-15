"""Transactional after-sales task writer with loss-aware remarks."""

from ...repositories.base import now_iso
from .member_matching import token_for
from .persistence_common import (
    CLEAR, CLEAR_TOKEN, action_for, apply_archive_action, selected_value, upsert,
)
from .related_common import finish_record, local_record, row_version


def write_after_task(conn, canonical, context, actor_id, batch_id, ids, counts, item):
    local_id, existed = local_record(conn, canonical, "after_sales_tasks", item)
    action = action_for(item)
    if action in {"ARCHIVE", "RESTORE"} and not existed:
        raise ValueError(f"Cannot {action.lower()} unknown after-sales task {item['external_key']}")
    if not apply_archive_action(conn, "after_sales_tasks", local_id, action, actor_id):
        _upsert_after_task(conn, local_id, existed, context, actor_id, ids, item)
    finish_record(
        conn, canonical, "after_sales_tasks", item, local_id, batch_id, ids, counts, existed
    )


def _upsert_after_task(conn, local_id, existed, context, actor_id, ids, item):
    token, now = token_for(item, "task_assignee"), now_iso()
    current = conn.execute(
        "SELECT remarks FROM after_sales_tasks WHERE id = ?", (local_id,)
    ).fetchone()
    issue_type = _issue_type(item.get("issue_type"), existed)
    description = selected_value(item, "issue_description")
    if description is None and not existed:
        description = "Imported after-sales issue"
    values = {
        "lead_id": ids["leads"][item["lead_key"]],
        "assignee_id": (CLEAR if token == CLEAR_TOKEN else
                        context["member_ids"].get((token, "task_assignee")) if token else None),
        "issue_type": issue_type, "status": _status(item.get("status"), existed),
        "issue_description": description,
        "solution": selected_value(item, "solution") or selected_value(item, "progress_text"),
        "customer_satisfaction": selected_value(item, "customer_satisfaction"),
        "lessons_learned": selected_value(item, "lessons_learned"),
        "remarks": _remarks(item, current[0] if current else None),
        "due_date": selected_value(item, "due_date"),
        "updated_at": now, "updated_by": actor_id,
    }
    if existed:
        values["row_version"] = row_version(conn, "after_sales_tasks", local_id) + 1
    else:
        values.update({"created_at": item.get("issue_date") or now, "created_by": actor_id,
                       "row_version": 1, "archived_at": None})
    upsert(conn, "after_sales_tasks", local_id, values)


def _status(value, existed):
    if value in (None, ""):
        return None if existed else "Open"
    if value not in {"Open", "In Progress", "Resolved", "Closed"}:
        raise ValueError(f"Invalid after-sales task status: {value}")
    return value


def _issue_type(value, existed):
    if value in (None, ""):
        return None if existed else "Other"
    if value not in {"Technical", "Quality", "Delivery", "Other"}:
        raise ValueError(f"Invalid after-sales issue type: {value}")
    return value


def _remarks(item, existing):
    tracked = (("contact_method", "Contact method"),
               ("contact_method_raw", "Contact method source"),
               ("progress_text", "Progress"))
    changed = "remarks" in item or any(field in item for field, _label in tracked)
    if not changed:
        return None
    lines = str(existing or "").splitlines()
    if "remarks" in item:
        value = item.get("remarks")
        lines = [] if value == CLEAR_TOKEN else ([str(value)] if value else lines)
    for field, label in tracked:
        if field not in item:
            continue
        lines = [line for line in lines if not line.startswith(f"{label}:")]
        value = item.get(field)
        if value not in (None, "", CLEAR_TOKEN):
            lines.append(f"{label}: {value}")
    result = "\n".join(lines).strip()
    return result if result else CLEAR
