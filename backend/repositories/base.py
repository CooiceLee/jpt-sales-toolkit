"""
Base repository with database connection management.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional, Union
from uuid import uuid4

from .authorization_schema import (
    DEFAULT_ORGANIZATION_ID,
    apply_authorization_schema_migration,
)
from .import_governance_schema import apply_import_governance_schema
from .member_identity_schema import apply_member_identity_schema
from .tech_task_exchange_schema import (
    apply_tech_task_exchange_result_snapshot_schema,
    apply_tech_task_exchange_schema,
)
from .trip_planning_schema import (
    apply_trip_planning_schema_v4,
    apply_trip_planning_schema_v5,
    apply_trip_planning_schema_v6,
    apply_trip_planning_schema_v7,
    apply_trip_planning_schema_v8,
    apply_trip_planning_schema_v9,
)

# Database connection singleton
_db_path: Optional[Path] = None
_connection: Optional[sqlite3.Connection] = None
_connection_init_lock = threading.RLock()
_SQLITE_BUSY_TIMEOUT_MS = 5000
APP_SCHEMA_VERSION = 9
APP_SCHEMA_MIGRATIONS = (
    # Historical migration numbers are immutable. Future schema versions must
    # append a new explicit tuple instead of rebinding the v1 record.
    (1, "runtime_schema_v1"),
    (2, "tech_task_exchange_v1"),
    (3, "tech_task_exchange_result_snapshot_v1"),
    (4, "trip_plan_legs_v1"),
    (5, "trip_plan_free_stops_v1"),
    (6, "trip_plan_half_day_schedule_v1"),
    (7, "trip_plan_flight_airports_v1"),
    (8, "trip_plan_team_members_v1"),
    (9, "trip_plan_accepted_times_v1"),
)
_APP_SCHEMA_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS app_schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    app_version TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""
_RUNTIME_REQUIRED_TABLES = {
    "organizations",
    "user_credentials",
    "device_authorizations",
    "authorization_events",
    "member_import_aliases",
    "import_batches",
    "import_bindings",
    "data_quality_issues",
    "customer_domains",
    "customer_aliases",
    "trip_plans",
    "trip_plan_stops",
    "trip_plan_legs",
    "trip_plan_free_stops",
    "trip_visit_briefings",
    "trip_plan_members",
    "tech_task_exchange_batches",
    "tech_task_exchange_bindings",
}
_RUNTIME_REQUIRED_COLUMNS = {
    "customers": {
        "normalized_address",
        "geocode_source",
        "geocode_confidence",
        "geocode_locked",
    },
    "lead_activities": {"archived_at"},
    "customer_contacts": {"archived_at"},
    "tech_task_exchange_bindings": {"last_exported_result_snapshot_json"},
    "pre_sales_tasks": {"client_request_id"},
    "leads": {"primary_contact_id", "quantity_text"},
    "after_sales_tasks": {"customer_satisfaction", "lessons_learned", "remarks"},
    "customer_domains": {"updated_at", "updated_by", "archived_at"},
    "customer_aliases": {"updated_at", "updated_by", "archived_at"},
    "trip_plans": {
        "route_order_mode",
        "transport_mode_priority",
        "departure_window_start",
        "departure_window_end",
        "return_window_start",
        "return_window_end",
    },
    "trip_plan_stops": {
        "duration_half_days", "preferred_period", "planned_start_period",
        "planned_end_period", "schedule_locked", "confirmation_status",
    },
    "trip_plan_free_stops": {
        "duration_half_days", "preferred_period", "planned_start_period",
        "planned_end_period", "schedule_locked", "confirmation_status",
    },
    "trip_plan_legs": {
        "from_free_stop_id", "to_free_stop_id", "travel_half_days",
        "manual_travel_half_days", "planned_start_date", "planned_start_period",
        "planned_end_date", "planned_end_period",
    },
    "trip_visit_briefings": {
        "stop_id", "timezone", "location_json", "customer_team_json",
        "contacts_json", "participants_json", "channel_partner_companions_json",
        "equipment_json", "agenda_items_json", "row_version",
    },
}
_RUNTIME_REQUIRED_INDEXES = {
    "idx_pre_sales_client_request",
    "idx_users_username_nocase",
    "idx_device_auth_active_device",
    "idx_data_quality_issues_batch",
    "idx_tech_exchange_batches_recipient",
    "idx_tech_exchange_bindings_local",
    "idx_trip_legs_active_member_key",
    "idx_trip_legs_active_shared_key",
    "idx_trip_legs_plan_sequence",
    "idx_trip_free_stops_plan",
    "idx_trip_visit_briefings_stop",
}


def _open_connection(
    db_path: Path,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open a consistently configured SQLite connection."""
    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=check_same_thread,
        cached_statements=0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MS}")
    return conn


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Check whether a table already contains a column."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check whether a table exists."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    """Add a missing column for lightweight runtime migrations."""
    if not _column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def _app_schema_version(conn: sqlite3.Connection) -> int:
    """Read the newest audited application-schema version."""
    if not _table_exists(conn, "app_schema_migrations"):
        return 0
    row = conn.execute("SELECT MAX(version) FROM app_schema_migrations").fetchone()
    return int(row[0] or 0)


def read_app_schema_version(db_path: Union[Path, str]) -> int:
    """Inspect a database without creating or migrating it."""
    path = Path(db_path)
    if not path.is_file():
        return 0
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return _app_schema_version(conn)
    finally:
        conn.close()


def _runtime_schema_has_drift(conn: sqlite3.Connection) -> bool:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if not _RUNTIME_REQUIRED_TABLES <= tables:
        return True
    for table, columns in _RUNTIME_REQUIRED_COLUMNS.items():
        if table not in tables:
            return True
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not columns <= existing:
            return True
    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }
    return not _RUNTIME_REQUIRED_INDEXES <= indexes


def database_requires_schema_migration(db_path: Union[Path, str]) -> bool:
    """Read-only check used to decide whether startup must back up first."""
    path = Path(db_path)
    if not path.is_file():
        return False
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return (
            _app_schema_version(conn) < APP_SCHEMA_VERSION
            or _runtime_schema_has_drift(conn)
        )
    finally:
        conn.close()


def _validate_app_schema_ledger(conn: sqlite3.Connection) -> None:
    expected = dict(APP_SCHEMA_MIGRATIONS)
    rows = conn.execute(
        "SELECT version, name FROM app_schema_migrations ORDER BY version"
    ).fetchall()
    for version, name in rows:
        if version not in expected:
            raise RuntimeError(
                f"Database schema version {version} is newer than this application"
            )
        if expected[version] != name:
            raise RuntimeError(
                f"Application schema version {version} belongs to {name!r}, "
                f"expected {expected[version]!r}"
            )
    recorded_versions = [int(row[0]) for row in rows]
    expected_prefix = [version for version, _ in APP_SCHEMA_MIGRATIONS][
        : len(recorded_versions)
    ]
    if recorded_versions != expected_prefix:
        raise RuntimeError(
            "Application schema ledger has a gap: "
            f"recorded={recorded_versions}, expected={expected_prefix}"
        )


def _apply_runtime_schema_v1(conn: sqlite3.Connection) -> None:
    """Bring pre-ledger desktop databases to the v1 runtime schema."""
    _ensure_column(conn, "customers", "normalized_address", "TEXT")
    _ensure_column(conn, "customers", "geocode_source", "TEXT")
    _ensure_column(conn, "customers", "geocode_confidence", "TEXT")
    _ensure_column(conn, "customers", "geocode_locked", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "lead_activities", "archived_at", "TEXT")
    _ensure_column(conn, "customer_contacts", "archived_at", "TEXT")
    if _table_exists(conn, "pre_sales_tasks"):
        _ensure_column(conn, "pre_sales_tasks", "client_request_id", "TEXT")
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_pre_sales_client_request
               ON pre_sales_tasks(lead_id, client_request_id)
               WHERE client_request_id IS NOT NULL"""
        )
    _repair_owner_assignments(conn)
    _repair_followup_stage_from_activities(conn)
    _repair_service_status_from_tasks(conn)
    _ensure_trip_planning_tables(conn)
    apply_authorization_schema_migration(conn)
    apply_member_identity_schema(conn)
    apply_import_governance_schema(conn)


def _apply_runtime_schema_v2(conn: sqlite3.Connection) -> None:
    """Add the isolated Leader/Tech task-package ledger and bindings."""
    apply_tech_task_exchange_schema(conn)


def _apply_runtime_schema_v3(conn: sqlite3.Connection) -> None:
    """Track the last result state exported by each Tech binding."""
    apply_tech_task_exchange_result_snapshot_schema(conn)


def _apply_runtime_schema_v4(conn: sqlite3.Connection) -> None:
    """Add first-class itinerary legs and route-planning preferences."""
    apply_trip_planning_schema_v4(conn)


def _apply_runtime_schema_v5(conn: sqlite3.Connection) -> None:
    """Add route stops that do not depend on customer or Lead records."""
    apply_trip_planning_schema_v5(conn)


def _apply_runtime_schema_v6(conn: sqlite3.Connection) -> None:
    """Add half-day scheduling and visit-briefing contracts."""
    apply_trip_planning_schema_v6(conn)


def _apply_runtime_schema_v7(conn: sqlite3.Connection) -> None:
    """Record the departure and arrival airports of a flown leg."""
    apply_trip_planning_schema_v7(conn)


def _apply_runtime_schema_v8(conn: sqlite3.Connection) -> None:
    """Record the travelling team and attribute each leg to a member."""
    apply_trip_planning_schema_v8(conn)


def _apply_runtime_schema_v9(conn: sqlite3.Connection) -> None:
    """Tell a time somebody accepted from one the calculation produced."""
    apply_trip_planning_schema_v9(conn)


def _repair_current_runtime_schema(conn: sqlite3.Connection) -> None:
    """Reapply every idempotent runtime step when drift is detected."""
    _apply_runtime_schema_v1(conn)
    _apply_runtime_schema_v2(conn)
    _apply_runtime_schema_v3(conn)
    _apply_runtime_schema_v4(conn)
    _apply_runtime_schema_v5(conn)
    _apply_runtime_schema_v6(conn)
    _apply_runtime_schema_v7(conn)
    _apply_runtime_schema_v8(conn)
    _apply_runtime_schema_v9(conn)


def _apply_runtime_migrations(conn: sqlite3.Connection, app_version: str) -> None:
    """Apply audited, transactional and idempotent runtime migrations."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(_APP_SCHEMA_LEDGER_DDL)
        _validate_app_schema_ledger(conn)
        current = _app_schema_version(conn)
        migration_steps = {
            1: _apply_runtime_schema_v1,
            2: _apply_runtime_schema_v2,
            3: _apply_runtime_schema_v3,
            4: _apply_runtime_schema_v4,
            5: _apply_runtime_schema_v5,
            6: _apply_runtime_schema_v6,
            7: _apply_runtime_schema_v7,
            8: _apply_runtime_schema_v8,
            9: _apply_runtime_schema_v9,
        }
        for version, name in APP_SCHEMA_MIGRATIONS:
            if version <= current:
                continue
            migration_steps[version](conn)
            conn.execute(
                "INSERT INTO app_schema_migrations "
                "(version, name, app_version, applied_at) VALUES (?, ?, ?, ?)",
                (
                    version,
                    name,
                    app_version,
                    now_iso(),
                ),
            )
            current = version
        if current == APP_SCHEMA_VERSION and _runtime_schema_has_drift(conn):
            _repair_current_runtime_schema(conn)
        if int(conn.execute("PRAGMA user_version").fetchone()[0]) != current:
            conn.execute(f"PRAGMA user_version = {current}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _ensure_trip_planning_tables(conn: sqlite3.Connection) -> None:
    """Create v0.7 trip planning tables for existing local databases."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trip_plans (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL REFERENCES users(id),
            start_date TEXT,
            end_date TEXT,
            region TEXT,
            origin_name TEXT,
            origin_lat REAL,
            origin_lng REAL,
            destination_name TEXT,
            destination_lat REAL,
            destination_lng REAL,
            travel_mode TEXT NOT NULL DEFAULT 'auto',
            avoid_weekends INTEGER NOT NULL DEFAULT 1,
            holiday_dates TEXT,
            itinerary_generated_at TEXT,
            itinerary_summary TEXT,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'Draft' CHECK (
                status IN ('Draft', 'Active', 'Completed')
            ),
            archived_at TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT REFERENCES users(id),
            updated_at TEXT NOT NULL,
            updated_by TEXT REFERENCES users(id),
            row_version INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trip_plan_stops (
            id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES trip_plans(id),
            customer_id TEXT NOT NULL REFERENCES customers(id),
            lead_id TEXT REFERENCES leads(id),
            sequence_no INTEGER NOT NULL DEFAULT 1,
            planned_date TEXT,
            planned_end_date TEXT,
            stay_days INTEGER NOT NULL DEFAULT 1,
            travel_from_label TEXT,
            travel_mode TEXT,
            travel_distance_km REAL,
            travel_time_hours REAL,
            travel_days INTEGER,
            visit_purpose TEXT,
            notes TEXT,
            result_status TEXT NOT NULL DEFAULT 'Planned' CHECK (
                result_status IN ('Planned', 'Visited', 'Follow-up Needed', 'Skipped')
            ),
            result_notes TEXT,
            result_activity_id TEXT REFERENCES lead_activities(id),
            archived_at TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT REFERENCES users(id),
            updated_at TEXT NOT NULL,
            updated_by TEXT REFERENCES users(id),
            row_version INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    _ensure_column(conn, "trip_plan_stops", "result_activity_id", "TEXT REFERENCES lead_activities(id)")
    _ensure_column(conn, "trip_plans", "origin_name", "TEXT")
    _ensure_column(conn, "trip_plans", "origin_lat", "REAL")
    _ensure_column(conn, "trip_plans", "origin_lng", "REAL")
    _ensure_column(conn, "trip_plans", "destination_name", "TEXT")
    _ensure_column(conn, "trip_plans", "destination_lat", "REAL")
    _ensure_column(conn, "trip_plans", "destination_lng", "REAL")
    _ensure_column(conn, "trip_plans", "travel_mode", "TEXT NOT NULL DEFAULT 'auto'")
    _ensure_column(conn, "trip_plans", "avoid_weekends", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "trip_plans", "holiday_dates", "TEXT")
    _ensure_column(conn, "trip_plans", "itinerary_generated_at", "TEXT")
    _ensure_column(conn, "trip_plans", "itinerary_summary", "TEXT")
    _ensure_column(conn, "trip_plans", "row_version", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "trip_plan_stops", "planned_end_date", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "stay_days", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "trip_plan_stops", "travel_from_label", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "travel_mode", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "travel_distance_km", "REAL")
    _ensure_column(conn, "trip_plan_stops", "travel_time_hours", "REAL")
    _ensure_column(conn, "trip_plan_stops", "travel_days", "INTEGER")
    _ensure_column(conn, "trip_plan_stops", "visit_customer_needs", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "visit_competitor", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "visit_budget", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "visit_decision_maker", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "visit_next_action", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "visit_followup_due_date", "TEXT")
    _ensure_column(conn, "trip_plan_stops", "visit_sample_needed", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "trip_plan_stops", "visit_quote_needed", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "trip_plan_stops", "followup_activity_id", "TEXT REFERENCES lead_activities(id)")
    _ensure_column(conn, "trip_plan_stops", "row_version", "INTEGER NOT NULL DEFAULT 1")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trip_plans_owner ON trip_plans(owner_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trip_stops_plan ON trip_plan_stops(plan_id, sequence_no)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trip_stops_customer ON trip_plan_stops(customer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trip_stops_lead ON trip_plan_stops(lead_id)")


def _repair_owner_assignments(conn: sqlite3.Connection) -> None:
    """Keep leads.owner_id and active owner assignment in sync for older local DBs."""
    if not _table_exists(conn, "leads") or not _table_exists(conn, "lead_assignments"):
        return

    now = now_iso()
    leads = conn.execute(
        """
        SELECT id, owner_id
        FROM leads
        WHERE archived_at IS NULL AND owner_id IS NOT NULL
        """
    ).fetchall()

    for lead_id, owner_id in leads:
        active_owners = conn.execute(
            """
            SELECT id, user_id
            FROM lead_assignments
            WHERE lead_id = ? AND assignment_type = 'owner' AND archived_at IS NULL
            """,
            (lead_id,),
        ).fetchall()

        if len(active_owners) == 1 and active_owners[0][1] == owner_id:
            continue

        conn.execute(
            """
            UPDATE lead_assignments
            SET archived_at = ?
            WHERE lead_id = ? AND assignment_type = 'owner' AND archived_at IS NULL
            """,
            (now, lead_id),
        )

        archived_owner = conn.execute(
            """
            SELECT id
            FROM lead_assignments
            WHERE lead_id = ? AND user_id = ? AND assignment_type = 'owner'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (lead_id, owner_id),
        ).fetchone()

        if archived_owner:
            conn.execute(
                """
                UPDATE lead_assignments
                SET archived_at = NULL
                WHERE id = ?
                """,
                (archived_owner[0],),
            )
        else:
            conn.execute(
                """
                INSERT INTO lead_assignments
                    (id, lead_id, user_id, assignment_type, created_at, created_by, archived_at)
                VALUES (?, ?, ?, 'owner', ?, NULL, NULL)
                """,
                (generate_uuid(), lead_id, owner_id, now),
            )


def _repair_service_status_from_tasks(conn: sqlite3.Connection) -> None:
    """Keep lead service_status aligned with active after-sales tasks."""
    if not _table_exists(conn, "leads") or not _table_exists(conn, "after_sales_tasks"):
        return

    now = now_iso()
    rows = conn.execute(
        """
        SELECT lead_id, GROUP_CONCAT(status) AS statuses
        FROM after_sales_tasks
        WHERE archived_at IS NULL
        GROUP BY lead_id
        """
    ).fetchall()

    for lead_id, statuses_text in rows:
        statuses = set((statuses_text or "").split(","))
        if "Open" in statuses:
            service_status = "Open"
        elif "In Progress" in statuses:
            service_status = "In Progress"
        elif "Resolved" in statuses:
            service_status = "Resolved"
        elif "Closed" in statuses:
            service_status = "Closed"
        else:
            service_status = "None"

        conn.execute(
            """
            UPDATE leads
            SET service_status = ?, updated_at = ?
            WHERE id = ? AND archived_at IS NULL AND service_status != ?
            """,
            (service_status, now, lead_id, service_status),
        )


def _repair_followup_stage_from_activities(conn: sqlite3.Connection) -> None:
    """Move leads with formal follow-ups into the follow-up stage."""
    if not _table_exists(conn, "leads") or not _table_exists(conn, "lead_activities"):
        return

    now = now_iso()
    conn.execute(
        """
        UPDATE leads
        SET sales_stage = 'Following',
            updated_at = ?,
            row_version = row_version + 1
        WHERE archived_at IS NULL
          AND sales_stage IN ('New', 'Assigned')
          AND EXISTS (
              SELECT 1
              FROM lead_activities a
              WHERE a.lead_id = leads.id
                AND a.action_type = 'follow_up'
                AND a.archived_at IS NULL
          )
        """,
        (now,),
    )


def init_db(db_path: Union[Path, str], app_version: Optional[str] = None) -> None:
    """Initialize database path and create schema if needed."""
    global _db_path
    with _connection_init_lock:
        _db_path = Path(db_path)
        is_new_database = not _db_path.exists()
        conn = _open_connection(_db_path)
        try:
            if is_new_database:
                schema_path = Path(__file__).parent.parent / "schema.sql"
                if schema_path.exists():
                    with open(schema_path, "r", encoding="utf-8") as f:
                        conn.executescript(f.read())
            if app_version is None:
                from ..config import APP_VERSION

                app_version = APP_VERSION
            _apply_runtime_migrations(conn, app_version)
        finally:
            conn.close()


def get_db() -> sqlite3.Connection:
    """Get database connection (creates if needed)."""
    global _connection
    if _connection is None:
        with _connection_init_lock:
            if _connection is None:
                if _db_path is None:
                    raise RuntimeError("Database not initialized. Call init_db() first.")
                _connection = _open_connection(
                    _db_path,
                    check_same_thread=False,
                )
    return _connection


@contextmanager
def request_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Yield an isolated connection owned by one request and close it afterward."""
    with _connection_init_lock:
        db_path = _db_path
    if db_path is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    conn = _open_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def close_db() -> None:
    """Close the shared database connection so the database file can be replaced."""
    global _connection
    with _connection_init_lock:
        if _connection is not None:
            _connection.close()
            _connection = None


@contextmanager
def get_transaction() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database transactions."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


def now_iso() -> str:
    """Return current timestamp in ISO format."""
    return datetime.utcnow().isoformat()


class ConflictError(Exception):
    """Raised when row_version conflict detected."""

    def __init__(self, current_version: int, your_version: int, current_data: dict):
        self.current_version = current_version
        self.your_version = your_version
        self.current_data = current_data
        super().__init__(f"Version conflict: current={current_version}, yours={your_version}")


class NotFoundError(Exception):
    """Raised when entity not found."""
    pass


class BaseRepository:
    """Base repository with common CRUD operations."""

    table_name: str = ""
    id_column: str = "id"

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or get_db()

    def get_by_id(self, entity_id: str) -> Optional[dict]:
        """Get entity by ID."""
        cursor = self.conn.execute(
            f"SELECT * FROM {self.table_name} WHERE {self.id_column} = ?",
            (entity_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def exists(self, entity_id: str) -> bool:
        """Check if entity exists."""
        cursor = self.conn.execute(
            f"SELECT 1 FROM {self.table_name} WHERE {self.id_column} = ?",
            (entity_id,),
        )
        return cursor.fetchone() is not None

    def delete_by_id(self, entity_id: str) -> bool:
        """Hard delete entity (use archive for soft delete)."""
        cursor = self.conn.execute(
            f"DELETE FROM {self.table_name} WHERE {self.id_column} = ?",
            (entity_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def count(self, where_clause: str = "", params: tuple = ()) -> int:
        """Count entities with optional filter."""
        sql = f"SELECT COUNT(*) FROM {self.table_name}"
        if where_clause:
            sql += f" WHERE {where_clause}"
        cursor = self.conn.execute(sql, params)
        return cursor.fetchone()[0]

    def _build_insert(self, data: dict) -> tuple[str, tuple]:
        """Build INSERT SQL from dict."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        return sql, tuple(data.values())

    def _build_update(
        self, entity_id: str, data: dict, check_version: Optional[int] = None
    ) -> tuple[str, tuple]:
        """Build UPDATE SQL from dict."""
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        sql = f"UPDATE {self.table_name} SET {set_clause} WHERE {self.id_column} = ?"
        params = list(data.values()) + [entity_id]

        if check_version is not None:
            sql += " AND row_version = ?"
            params.append(check_version)

        return sql, tuple(params)
