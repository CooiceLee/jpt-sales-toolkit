"""Non-destructive runtime migration for import-governance data."""

from __future__ import annotations

from .import_governance_ddl import (
    CUSTOMER_RELATION_DDL,
    IMPORT_GOVERNANCE_DDL,
    INDEX_DDL,
)


CORE_COLUMNS = (
    ("leads", "primary_contact_id", "TEXT REFERENCES customer_contacts(id)"),
    ("leads", "quantity_text", "TEXT"),
    ("after_sales_tasks", "customer_satisfaction", "TEXT"),
    ("after_sales_tasks", "lessons_learned", "TEXT"),
    ("after_sales_tasks", "remarks", "TEXT"),
)

RELATION_COLUMNS = (
    ("customer_domains", "updated_at", "TEXT"),
    ("customer_domains", "updated_by", "TEXT REFERENCES users(id)"),
    ("customer_domains", "archived_at", "TEXT"),
    ("customer_aliases", "updated_at", "TEXT"),
    ("customer_aliases", "updated_by", "TEXT REFERENCES users(id)"),
    ("customer_aliases", "archived_at", "TEXT"),
)


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    if _table_exists(conn, table) and not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def apply_import_governance_schema(conn) -> None:
    """Create import metadata and add nullable business fields without rewriting rows."""
    for statement in CUSTOMER_RELATION_DDL:
        conn.execute(statement)
    for table, column, definition in CORE_COLUMNS + RELATION_COLUMNS:
        _ensure_column(conn, table, column, definition)
    for table in ("customer_domains", "customer_aliases"):
        conn.execute(
            f"UPDATE {table} SET updated_at = created_at "
            "WHERE updated_at IS NULL AND created_at IS NOT NULL"
        )
    for statement in IMPORT_GOVERNANCE_DDL + INDEX_DDL:
        conn.execute(statement)
