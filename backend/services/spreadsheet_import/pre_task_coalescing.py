"""Coalesce legacy pre-sales assignee aliases after account resolution."""

from __future__ import annotations

from .member_matching import token_for
from .persistence_common import CLEAR_TOKEN

_IDENTITY_FIELDS = {
    "external_key", "assignee_username_token", "assignee_name_raw",
    "_binding_external_keys", "_source_assignee_names",
}


def coalesce_pre_sales_tasks(entities: dict, member_ids: dict) -> dict:
    """Return one physical task per source-row group and resolved Tech account."""
    grouped, tasks = {}, []
    for original in entities.get("pre_sales_tasks") or []:
        item = dict(original)
        identity = _resolved_group_identity(item, member_ids)
        if identity is None:
            tasks.append(item)
            continue
        existing = grouped.get(identity)
        if existing is None:
            item["_binding_external_keys"] = [item["external_key"]]
            item["_source_assignee_names"] = _assignee_names(item)
            grouped[identity] = item
            tasks.append(item)
            continue
        _merge_same_source_task(existing, item)
    return {**entities, "pre_sales_tasks": tasks}


def _resolved_group_identity(item: dict, member_ids: dict):
    if str(item.get("action") or "UPSERT").upper() != "UPSERT":
        return None
    group_key, lead_key = item.get("task_group_key"), item.get("lead_key")
    token = token_for(item, "task_assignee")
    assignee_id = member_ids.get((token, "task_assignee"))
    if not group_key or not lead_key or not token or token == CLEAR_TOKEN or not assignee_id:
        return None
    return str(group_key), str(lead_key), str(assignee_id)


def _merge_same_source_task(target: dict, incoming: dict) -> None:
    key = incoming.get("external_key")
    if key and key not in target["_binding_external_keys"]:
        target["_binding_external_keys"].append(key)
    for name in _assignee_names(incoming):
        if name not in target["_source_assignee_names"]:
            target["_source_assignee_names"].append(name)
    for field, value in incoming.items():
        if field in _IDENTITY_FIELDS or value in (None, ""):
            continue
        if target.get(field) in (None, ""):
            target[field] = value


def _assignee_names(item: dict) -> list[str]:
    value = str(item.get("assignee_name_raw") or "").strip()
    return [value] if value else []
