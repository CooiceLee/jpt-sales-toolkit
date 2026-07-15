"""Fresh/legacy database contracts for import identity governance."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from backend.repositories import close_db, init_db
from test_authorization_data_layer import _create_legacy_database


NEW_TABLES = {
    "member_import_aliases", "import_batches", "import_bindings", "data_quality_issues",
}

def columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

def assert_expected_schema(conn) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert NEW_TABLES <= tables
    assert {"primary_contact_id", "quantity_text"} <= columns(conn, "leads")
    assert {"customer_satisfaction", "lessons_learned", "remarks"} <= columns(
        conn, "after_sales_tasks"
    )
    lifecycle = {"updated_at", "updated_by", "archived_at"}
    assert lifecycle <= columns(conn, "customer_domains")
    assert lifecycle <= columns(conn, "customer_aliases")

def seed_old_relations(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        INSERT INTO customers(id) VALUES ('customer-1');
        CREATE TABLE customer_domains (
            id TEXT PRIMARY KEY, customer_id TEXT, domain TEXT, is_primary INTEGER,
            created_at TEXT, UNIQUE(customer_id, domain)
        );
        CREATE TABLE customer_aliases (
            id TEXT PRIMARY KEY, customer_id TEXT, alias_name TEXT,
            normalized_alias TEXT, created_at TEXT, UNIQUE(customer_id, normalized_alias)
        );
        INSERT INTO customer_domains VALUES (
            'domain-1','customer-1','example.com',1,'2025-01-01T00:00:00'
        );
        INSERT INTO customer_aliases VALUES (
            'alias-1','customer-1','Old Name','old name','2025-01-02T00:00:00'
        );
        """
    )
    conn.commit()
    conn.close()

def assert_old_database_migrates() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "legacy.sqlite"
        expected_users = _create_legacy_database(db_path)
        seed_old_relations(db_path)
        close_db()
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        assert_expected_schema(conn)
        assert conn.execute("SELECT * FROM users ORDER BY id").fetchall() == sorted(expected_users)
        assert conn.execute("SELECT domain FROM customer_domains").fetchone()[0] == "example.com"
        assert conn.execute("SELECT updated_at FROM customer_domains").fetchone()[0].startswith("2025-01-01")
        assert conn.execute("SELECT alias_name FROM customer_aliases").fetchone()[0] == "Old Name"
        try:
            conn.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)",
                ("case-copy", "LEADER.OLD", "hash", "Copy", "sales", None, 1,
                 "2025-03-01T00:00:00", None),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("legacy users table must gain case-insensitive uniqueness")
        conn.close()
        close_db()

def assert_collision_fails_without_rebinding() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "collision.sqlite"
        _create_legacy_database(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)",
            ("collision-user", "LEADER.OLD", "hash", "Other", "sales", None, 1,
             "2025-03-01T00:00:00", None),
        )
        conn.execute("ALTER TABLE lead_assignments ADD COLUMN created_by TEXT")
        conn.execute(
            "INSERT INTO leads VALUES (?,?,?,?,?,?,?)",
            ("lead-1", "legacy-leader", "New", "None", None, "2025-03-01", 1),
        )
        conn.commit()
        conn.close()
        close_db()
        try:
            init_db(db_path)
        except RuntimeError as exc:
            assert "no user IDs or foreign keys were changed" in str(exc)
        else:
            raise AssertionError("case-colliding legacy accounts must stop migration")
        conn = sqlite3.connect(db_path)
        assert {row[0] for row in conn.execute("SELECT id FROM users")} == {
            "legacy-leader", "legacy-tech", "collision-user",
        }
        assert conn.execute("SELECT owner_id FROM leads WHERE id='lead-1'").fetchone()[0] == "legacy-leader"
        assert conn.execute("SELECT COUNT(*) FROM lead_assignments").fetchone()[0] == 0
        conn.close()
        close_db()

def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "fresh.sqlite"
        close_db(); init_db(db_path)
        conn = sqlite3.connect(db_path); assert_expected_schema(conn); conn.close(); close_db()
    assert_old_database_migrates()
    assert_collision_fails_without_rebinding()
    print("PASS: import identity schema preserves legacy data and rejects username collisions")


if __name__ == "__main__":
    main()
