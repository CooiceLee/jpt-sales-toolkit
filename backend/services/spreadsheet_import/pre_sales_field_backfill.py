"""Plan and apply lossless backfills for bound Excel pre-sales tasks."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from ...repositories.base import generate_uuid, now_iso
from ..importing import parse_import_workbook
from .write_pre_tasks import REQUEST_FIELDS, RESULT_FIELDS


def parse_object(raw_value: object, task_id: str, field_name: str) -> dict:
    try:
        value = json.loads(raw_value or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{task_id} has invalid {field_name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{task_id} has non-object {field_name}")
    return value


def load_backfill_plan(
    conn: sqlite3.Connection, workbook: Path
) -> tuple[dict, list[dict], list, list]:
    canonical = parse_import_workbook(workbook.read_bytes(), workbook.name)
    plans, unbound, preserved = {}, [], []
    for item in canonical["entities"].get("pre_sales_tasks") or []:
        row = conn.execute(
            """SELECT t.* FROM import_bindings b
               JOIN pre_sales_tasks t ON t.id = b.local_entity_id
               WHERE b.dataset_id = ? AND b.entity_type = 'pre_sales_tasks'
                 AND b.external_key = ?""",
            (canonical["dataset_id"], item["external_key"]),
        ).fetchone()
        if row is None:
            unbound.append(item["external_key"])
            continue
        task_id = row["id"]
        plan = plans.setdefault(task_id, {
            "task_id": task_id, "request_updates": {}, "result_updates": {},
            "external_keys": [], "source_refs": [],
        })
        plan["external_keys"].append(item["external_key"])
        plan["source_refs"].append(item["source_ref"])
        request = parse_object(row["request_json"], task_id, "request_json")
        result = parse_object(row["result_json"], task_id, "result_json")
        _collect(plan, request, item, REQUEST_FIELDS, "request_updates", preserved)
        _collect(plan, result, item, RESULT_FIELDS, "result_updates", preserved)
    active = [
        plan for plan in plans.values()
        if plan["request_updates"] or plan["result_updates"]
    ]
    return canonical, active, unbound, preserved


def _collect(plan, current, source, fields, target_key, preserved):
    updates = plan[target_key]
    for field in fields:
        expected = source.get(field)
        if expected in (None, ""):
            continue
        actual = updates.get(field, current.get(field))
        if actual in (None, ""):
            updates[field] = expected
        elif actual != expected:
            preserved.append({
                "task_id": plan["task_id"], "field": field,
                "source_value": expected, "current_value": actual,
            })


def apply_backfill_plan(
    conn: sqlite3.Connection, plans: list[dict], actor_id: str
) -> dict:
    now, applied_tasks, applied_fields = now_iso(), 0, Counter()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for plan in plans:
            row = conn.execute(
                "SELECT * FROM pre_sales_tasks WHERE id = ?", (plan["task_id"],)
            ).fetchone()
            request = parse_object(row["request_json"], row["id"], "request_json")
            result = parse_object(row["result_json"], row["id"], "result_json")
            actual = _merge_missing(plan, request, result, applied_fields)
            if not actual["request_json"] and not actual["result_json"]:
                continue
            conn.execute(
                """UPDATE pre_sales_tasks SET request_json = ?, result_json = ?,
                   updated_at = ?, updated_by = ?, row_version = row_version + 1
                   WHERE id = ?""",
                (json.dumps(request, ensure_ascii=False, sort_keys=True),
                 json.dumps(result, ensure_ascii=False, sort_keys=True),
                 now, actor_id, row["id"]),
            )
            conn.execute(
                """INSERT INTO audit_logs (
                       id, entity_type, entity_id, actor_id, event_type,
                       before_json, after_json, created_at
                   ) VALUES (?, 'pre_sales_task', ?, ?, 'backfill_import_fields',
                             ?, ?, ?)""",
                (generate_uuid(), row["id"], actor_id,
                 json.dumps(dict(row), ensure_ascii=False),
                 json.dumps(actual, ensure_ascii=False, sort_keys=True), now),
            )
            applied_tasks += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"tasks": applied_tasks, "fields": sum(applied_fields.values()),
            "field_counts": dict(sorted(applied_fields.items()))}


def _merge_missing(plan, request, result, applied_fields):
    actual = {"request_json": {}, "result_json": {}}
    for group, payload in (("request_json", request), ("result_json", result)):
        for field, value in plan[f"{group.removesuffix('_json')}_updates"].items():
            if payload.get(field) in (None, ""):
                payload[field] = value
                actual[group][field] = value
                applied_fields[field] += 1
    return actual
