"""Runtime schema for offline Leader/Tech task-package exchange."""

from __future__ import annotations

import sqlite3


TECH_TASK_EXCHANGE_DDL = """
CREATE TABLE IF NOT EXISTS tech_task_exchange_batches (
    package_id TEXT PRIMARY KEY,
    package_type TEXT NOT NULL CHECK (
        package_type IN ('tech_task_assignment', 'tech_task_results')
    ),
    direction TEXT NOT NULL CHECK (
        direction IN ('leader_to_tech', 'tech_to_leader')
    ),
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    source_user_id TEXT NOT NULL REFERENCES users(id),
    recipient_user_id TEXT NOT NULL REFERENCES users(id),
    parent_package_id TEXT,
    payload_sha256 TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('exported', 'imported')),
    created_at TEXT NOT NULL,
    imported_at TEXT,
    imported_by TEXT REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tech_task_exchange_bindings (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    task_type TEXT NOT NULL CHECK (task_type IN ('pre_sales', 'after_sales')),
    source_task_id TEXT NOT NULL,
    local_task_id TEXT NOT NULL,
    source_lead_id TEXT NOT NULL,
    local_lead_id TEXT NOT NULL REFERENCES leads(id),
    source_customer_id TEXT NOT NULL,
    local_customer_id TEXT NOT NULL REFERENCES customers(id),
    leader_user_id TEXT NOT NULL REFERENCES users(id),
    tech_user_id TEXT NOT NULL REFERENCES users(id),
    source_row_version INTEGER NOT NULL,
    source_snapshot_json TEXT NOT NULL,
    source_package_id TEXT NOT NULL,
    local_row_version_at_sync INTEGER NOT NULL,
    last_exported_local_row_version INTEGER,
    last_exported_result_snapshot_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(organization_id, task_type, source_task_id, tech_user_id)
);

CREATE INDEX IF NOT EXISTS idx_tech_exchange_batches_recipient
    ON tech_task_exchange_batches(recipient_user_id, direction, created_at);
CREATE INDEX IF NOT EXISTS idx_tech_exchange_bindings_local
    ON tech_task_exchange_bindings(task_type, local_task_id);
CREATE INDEX IF NOT EXISTS idx_tech_exchange_bindings_source_lead
    ON tech_task_exchange_bindings(organization_id, source_lead_id, tech_user_id);
"""


def apply_tech_task_exchange_schema(conn: sqlite3.Connection) -> None:
    """Create the additive v2 task-exchange schema idempotently."""
    # ``executescript`` may commit an already-open sqlite3 transaction. Apply
    # each self-contained statement so startup migration remains atomic.
    for statement in TECH_TASK_EXCHANGE_DDL.split(";"):
        if statement.strip():
            conn.execute(statement)


def apply_tech_task_exchange_result_snapshot_schema(
    conn: sqlite3.Connection,
) -> None:
    """Persist the exact task-result state last included in a Tech export."""
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(tech_task_exchange_bindings)")
    }
    if "last_exported_result_snapshot_json" not in columns:
        conn.execute(
            "ALTER TABLE tech_task_exchange_bindings "
            "ADD COLUMN last_exported_result_snapshot_json TEXT"
        )
