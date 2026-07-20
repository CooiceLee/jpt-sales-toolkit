#!/usr/bin/env python3
"""Soft-archive same-source pre-sales tasks collapsed onto one Tech account."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.repositories.base import generate_uuid, now_iso
from backend.services.importing import parse_import_workbook

SIGNATURE_FIELDS = (
    "lead_id", "assignee_id", "status", "due_date", "request_json", "result_json",
)


def load_plan(conn: sqlite3.Connection, workbook: Path) -> tuple[dict, list[dict]]:
    canonical = parse_import_workbook(workbook.read_bytes(), workbook.name)
    dataset_id = canonical["dataset_id"]
    source_groups = defaultdict(list)
    for item in canonical["entities"].get("pre_sales_tasks") or []:
        if item.get("task_group_key") and item.get("external_key"):
            source_groups[item["task_group_key"]].append(item["external_key"])

    repairs = []
    for group_key, external_keys in source_groups.items():
        rows = _bound_tasks(conn, dataset_id, external_keys)
        by_assignee = defaultdict(list)
        for row in rows:
            by_assignee[row["assignee_id"]].append(row)
        for assignee_id, candidates in by_assignee.items():
            distinct = {row["id"]: row for row in candidates}
            active = [row for row in distinct.values() if not row["archived_at"]]
            if len(active) < 2 or not _same_signature(active):
                continue
            ordered = sorted(active, key=lambda row: (row["created_at"], row["id"]))
            survivor, duplicates = ordered[0], ordered[1:]
            keys = sorted({
                row["external_key"] for row in candidates
                if row["id"] in {item["id"] for item in ordered}
            })
            repairs.append({
                "task_group_key": group_key,
                "assignee_id": assignee_id,
                "survivor_id": survivor["id"],
                "duplicate_ids": [row["id"] for row in duplicates],
                "external_keys": keys,
                "lead_id": survivor["lead_id"],
            })
    return canonical, repairs


def _bound_tasks(conn, dataset_id: str, external_keys: list[str]) -> list[sqlite3.Row]:
    if not external_keys:
        return []
    marks = ", ".join("?" for _ in external_keys)
    return conn.execute(
        f"""SELECT t.*, b.external_key
            FROM import_bindings b
            JOIN pre_sales_tasks t ON t.id = b.local_entity_id
            WHERE b.dataset_id = ? AND b.entity_type = 'pre_sales_tasks'
              AND b.external_key IN ({marks})""",
        (dataset_id, *external_keys),
    ).fetchall()


def _same_signature(rows: list[sqlite3.Row]) -> bool:
    signatures = {
        tuple(row[field] for field in SIGNATURE_FIELDS)
        for row in rows
    }
    return len(signatures) == 1


def apply_plan(
    conn: sqlite3.Connection,
    dataset_id: str,
    repairs: list[dict],
    actor_id: str,
) -> None:
    now = now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for repair in repairs:
            for duplicate_id in repair["duplicate_ids"]:
                before = conn.execute(
                    "SELECT * FROM pre_sales_tasks WHERE id = ?", (duplicate_id,)
                ).fetchone()
                conn.execute(
                    """UPDATE pre_sales_tasks
                       SET archived_at = ?, updated_at = ?, updated_by = ?,
                           row_version = row_version + 1
                       WHERE id = ? AND archived_at IS NULL""",
                    (now, now, actor_id, duplicate_id),
                )
                conn.execute(
                    """UPDATE lead_activities SET archived_at = ?
                       WHERE action_type = 'task_update' AND archived_at IS NULL
                         AND json_extract(payload_json, '$.task_id') = ?""",
                    (now, duplicate_id),
                )
                conn.execute(
                    """INSERT INTO audit_logs (
                           id, entity_type, entity_id, actor_id, event_type,
                           before_json, after_json, created_at
                       ) VALUES (?, 'pre_sales_task', ?, ?, 'deduplicate_import',
                                 ?, ?, ?)""",
                    (
                        generate_uuid(), duplicate_id, actor_id,
                        json.dumps(dict(before), ensure_ascii=False),
                        json.dumps({
                            "archived_at": now,
                            "deduplicated_into": repair["survivor_id"],
                            "task_group_key": repair["task_group_key"],
                        }, ensure_ascii=False),
                        now,
                    ),
                )
            marks = ", ".join("?" for _ in repair["external_keys"])
            conn.execute(
                f"""UPDATE import_bindings
                    SET local_entity_id = ?, updated_at = ?
                    WHERE dataset_id = ? AND entity_type = 'pre_sales_tasks'
                      AND external_key IN ({marks})""",
                (
                    repair["survivor_id"], now, dataset_id,
                    *repair["external_keys"],
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--actor-id")
    parser.add_argument("--expected-duplicates", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    canonical, repairs = load_plan(conn, args.workbook)
    duplicate_count = sum(len(item["duplicate_ids"]) for item in repairs)
    report = {
        "dataset_id": canonical["dataset_id"],
        "source_hash": canonical["source_hash"],
        "duplicate_count": duplicate_count,
        "repairs": repairs,
        "applied": False,
    }
    if args.apply:
        if args.expected_duplicates is None or duplicate_count != args.expected_duplicates:
            raise SystemExit(
                f"Safety check failed: expected {args.expected_duplicates}, found {duplicate_count}"
            )
        actor = conn.execute(
            "SELECT role, is_active FROM users WHERE id = ?", (args.actor_id,)
        ).fetchone()
        if not actor or actor["role"] != "leader" or not actor["is_active"]:
            raise SystemExit("--actor-id must identify an active Leader")
        apply_plan(conn, canonical["dataset_id"], repairs, args.actor_id)
        report["applied"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
