#!/usr/bin/env python3
"""Backfill missing Excel pre-sales fields without overwriting later app edits."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.spreadsheet_import.pre_sales_field_backfill import (
    apply_backfill_plan,
    load_backfill_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--actor-id")
    parser.add_argument("--expected-tasks", type=int)
    parser.add_argument("--expected-fields", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    canonical, plans, unbound, preserved = load_backfill_plan(conn, args.workbook)
    field_counts = Counter(
        field for plan in plans
        for group in ("request_updates", "result_updates")
        for field in plan[group]
    )
    report = {
        "dataset_id": canonical["dataset_id"], "source_hash": canonical["source_hash"],
        "task_count": len(plans), "field_count": sum(field_counts.values()),
        "field_counts": dict(sorted(field_counts.items())),
        "unbound_count": len(unbound), "preserved_difference_count": len(preserved),
        "applied": False,
    }
    if args.apply:
        expected = (args.expected_tasks, args.expected_fields)
        if None in expected or expected != (len(plans), sum(field_counts.values())):
            raise SystemExit(f"Safety check failed: expected {expected}, found "
                             f"{(len(plans), sum(field_counts.values()))}")
        if unbound:
            raise SystemExit(f"Safety check failed: {len(unbound)} tasks are unbound")
        actor = conn.execute(
            "SELECT role, is_active FROM users WHERE id = ?", (args.actor_id,)
        ).fetchone()
        if not actor or actor["role"] != "leader" or not actor["is_active"]:
            raise SystemExit("--actor-id must identify an active Leader")
        report["applied_result"] = apply_backfill_plan(conn, plans, args.actor_id)
        report["applied"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
