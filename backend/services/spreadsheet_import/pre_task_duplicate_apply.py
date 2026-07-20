"""Transactional application of preflight-approved pre-sales deduplication."""

from __future__ import annotations

import json

from ...repositories.base import generate_uuid, now_iso
from .bindings import binding_id, external_keys
from .errors import SpreadsheetImportError
from .pre_task_duplicate_guard import has_active_task_updates
from .related_common import local_record


def resolve_pre_task_record(conn, canonical: dict, item: dict):
    keys = external_keys(item)
    if len(keys) == 1:
        local_id, existed = local_record(conn, canonical, "pre_sales_tasks", item)
        return local_id, existed, (), None
    rows = _bound_rows(conn, canonical["dataset_id"], keys)
    active = [row for row in rows if row["archived_at"] is None]
    plan = item.get("_dedupe_plan")
    if len(active) > 1:
        _verify_plan(active, plan)
        return (
            plan["survivor_id"],
            True,
            tuple(plan["duplicates"]),
            plan["survivor_row_version"],
        )
    existing = active or rows
    local_id = existing[0]["id"] if existing else generate_uuid()
    return local_id, bool(existing), (), None


def archive_planned_duplicates(
    conn, duplicates: tuple[dict, ...], survivor_id: str,
    actor_id: str, source_keys: tuple[str, ...],
) -> None:
    now = now_iso()
    for planned in duplicates:
        task_id, version = planned["id"], planned["row_version"]
        if has_active_task_updates(conn, task_id):
            raise _changed_error()
        before = conn.execute(
            "SELECT * FROM pre_sales_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        cursor = conn.execute(
            """UPDATE pre_sales_tasks
               SET archived_at = ?, updated_at = ?, updated_by = ?,
                   row_version = row_version + 1
               WHERE id = ? AND row_version = ? AND archived_at IS NULL""",
            (now, now, actor_id, task_id, version),
        )
        if before is None or cursor.rowcount != 1:
            raise _changed_error()
        conn.execute(
            """INSERT INTO audit_logs (
                   id, entity_type, entity_id, actor_id, event_type,
                   before_json, after_json, created_at
               ) VALUES (?, 'pre_sales_task', ?, ?, 'deduplicate_import', ?, ?, ?)""",
            (
                generate_uuid(), task_id, actor_id,
                json.dumps(dict(before), ensure_ascii=False, default=str),
                json.dumps({
                    "archived_at": now,
                    "deduplicated_into": survivor_id,
                    "source_external_keys": list(source_keys),
                }, ensure_ascii=False),
                now,
            ),
        )


def _bound_rows(conn, dataset_id: str, keys: tuple[str, ...]) -> list:
    ids = list(dict.fromkeys(
        binding_id(conn, dataset_id, "pre_sales_tasks", key) for key in keys
    ))
    ids = [value for value in ids if value]
    if not ids:
        return []
    marks = ", ".join("?" for _ in ids)
    return conn.execute(
        f"""SELECT id, archived_at, created_at, row_version
            FROM pre_sales_tasks WHERE id IN ({marks})
            ORDER BY archived_at IS NOT NULL, created_at, id""",
        ids,
    ).fetchall()


def _verify_plan(active: list, plan: object) -> None:
    if not isinstance(plan, dict):
        raise _changed_error()
    actual = {row["id"]: row["row_version"] for row in active}
    expected = {
        plan.get("survivor_id"): plan.get("survivor_row_version"),
        **{
            item.get("id"): item.get("row_version")
            for item in plan.get("duplicates") or []
        },
    }
    if actual != expected:
        raise _changed_error()


def _changed_error() -> SpreadsheetImportError:
    return SpreadsheetImportError(
        "pre_sales_duplicate_changed",
        "Pre-sales task data changed after preflight; run preflight again",
        409,
    )
