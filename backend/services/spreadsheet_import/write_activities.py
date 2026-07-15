"""Transactional lead-activity writer."""

from ...repositories.base import now_iso
from .member_matching import token_for
from .persistence_common import (
    CLEAR, CLEAR_TOKEN, action_for, apply_archive_action, selected_value, upsert,
)
from .persistence_json import merged_field_json
from .related_common import finish_record, local_record
from .value_normalization import boolean_value

ACTIVITY_TYPES = {"follow_up", "comment", "field_change", "assignment", "system", "task_update"}


def write_activity(conn, canonical, context, actor_id, batch_id, ids, counts, item):
    local_id, existed = local_record(conn, canonical, "activities", item)
    action = action_for(item)
    if action in {"ARCHIVE", "RESTORE"} and not existed:
        raise ValueError(f"Cannot {action.lower()} unknown activity {item['external_key']}")
    if not apply_archive_action(conn, "lead_activities", local_id, action, actor_id):
        _upsert_activity(conn, local_id, existed, context, ids, item)
    finish_record(
        conn, canonical, "activities", item, local_id, batch_id, ids, counts, existed
    )


def _upsert_activity(conn, local_id, existed, context, ids, item):
    token = token_for(item, "actor")
    activity_type = _activity_type(item, existed)
    known = {"external_key", "source_ref", "source_refs", "action", "lead_key",
             "activity_type", "action_type", "actor_username_token", "actor_name_raw",
             "occurred_at", "content", "summary", "visibility", "is_formal_follow_up"}
    current = conn.execute(
        "SELECT payload_json FROM lead_activities WHERE id = ?", (local_id,)
    ).fetchone()
    extras = tuple(key for key in item if key not in known)
    upsert(conn, "lead_activities", local_id, {
        "lead_id": ids["leads"][item["lead_key"]],
        "actor_id": (CLEAR if token == CLEAR_TOKEN else
                     context["member_ids"].get((token, "actor")) if token else None),
        "action_type": activity_type, "visibility": _visibility(item, existed),
        "is_formal_follow_up": _formal_follow_up(item, activity_type, existed),
        "summary": _summary(item, existed),
        "payload_json": merged_field_json(current[0] if current else None, item, extras),
        "created_at": _occurred_at(item, existed), "archived_at": None,
    })


def _activity_type(item, existed):
    value = item.get("activity_type") or item.get("action_type")
    if value in (None, ""):
        return None if existed else "comment"
    if value == CLEAR_TOKEN or value not in ACTIVITY_TYPES:
        raise ValueError(f"Invalid activity type: {value}")
    return value


def _visibility(item, existed):
    value = item.get("visibility")
    if value in (None, ""):
        return None if existed else "all"
    if value == CLEAR_TOKEN or value not in {"all", "internal", "owner_only"}:
        raise ValueError(f"Invalid activity visibility: {value}")
    return value


def _formal_follow_up(item, activity_type, existed):
    value = item.get("is_formal_follow_up")
    if value in (None, ""):
        return None if existed else int(activity_type == "follow_up")
    if value == CLEAR_TOKEN:
        raise ValueError("Activity follow-up flag cannot be cleared")
    return boolean_value(value)


def _summary(item, existed):
    value = selected_value(item, "content")
    value = selected_value(item, "summary") if value is None else value
    if value is CLEAR:
        raise ValueError("Activity summary cannot be cleared")
    return value if value is not None else (None if existed else "Imported activity")


def _occurred_at(item, existed):
    value = selected_value(item, "occurred_at")
    if value is CLEAR:
        raise ValueError("Activity occurred_at cannot be cleared")
    return value if value is not None else (None if existed else now_iso())
