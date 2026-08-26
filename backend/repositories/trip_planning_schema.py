"""Append-only Trip Planner schema migrations."""

from __future__ import annotations

import sqlite3


PLAN_COLUMNS = {
    "route_order_mode": "TEXT NOT NULL DEFAULT 'auto'",
    "transport_mode_priority": (
        "TEXT NOT NULL DEFAULT '[\"flight\",\"drive\",\"ground_public\"]'"
    ),
    "departure_window_start": "TEXT",
    "departure_window_end": "TEXT",
    "return_window_start": "TEXT",
    "return_window_end": "TEXT",
}

TRIP_PLAN_MEMBERS_DDL = """
CREATE TABLE IF NOT EXISTS trip_plan_members (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    origin_name_override TEXT,
    origin_lat_override REAL CHECK (origin_lat_override BETWEEN -90 AND 90),
    origin_lng_override REAL CHECK (origin_lng_override BETWEEN -180 AND 180),
    destination_name_override TEXT,
    destination_lat_override REAL CHECK (destination_lat_override BETWEEN -90 AND 90),
    destination_lng_override REAL CHECK (destination_lng_override BETWEEN -180 AND 180),
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
)
"""

TRIP_PLAN_LEGS_DDL = """
CREATE TABLE IF NOT EXISTS trip_plan_legs (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    leg_key TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    from_kind TEXT NOT NULL CHECK (from_kind IN ('origin', 'stop')),
    from_stop_id TEXT REFERENCES trip_plan_stops(id),
    from_label TEXT,
    to_kind TEXT NOT NULL CHECK (to_kind IN ('stop', 'destination')),
    to_stop_id TEXT REFERENCES trip_plan_stops(id),
    to_label TEXT,
    selected_mode TEXT NOT NULL CHECK (
        selected_mode IN ('flight', 'drive', 'ground_public', 'other')
    ),
    mode_locked INTEGER NOT NULL DEFAULT 0 CHECK (mode_locked IN (0, 1)),
    distance_km REAL NOT NULL DEFAULT 0 CHECK (distance_km >= 0),
    time_hours REAL NOT NULL DEFAULT 0 CHECK (time_hours >= 0),
    travel_days INTEGER NOT NULL DEFAULT 0 CHECK (travel_days >= 0),
    manual_distance_km REAL CHECK (manual_distance_km >= 0),
    manual_time_hours REAL CHECK (manual_time_hours >= 0),
    manual_travel_days INTEGER CHECK (manual_travel_days >= 0),
    notes TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
)
"""

TRIP_PLAN_FREE_STOPS_DDL = """
CREATE TABLE IF NOT EXISTS trip_plan_free_stops (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    category TEXT NOT NULL CHECK (
        category IN ('rest', 'hotel', 'airport', 'transit', 'meal', 'other')
    ),
    location_name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    country TEXT,
    lat REAL NOT NULL CHECK (lat >= -90 AND lat <= 90),
    lng REAL NOT NULL CHECK (lng >= -180 AND lng <= 180),
    sequence_no INTEGER NOT NULL DEFAULT 1,
    planned_date TEXT,
    planned_end_date TEXT,
    stay_days INTEGER NOT NULL DEFAULT 1 CHECK (stay_days >= 1 AND stay_days <= 30),
    travel_from_label TEXT,
    travel_mode TEXT,
    travel_distance_km REAL,
    travel_time_hours REAL,
    travel_days INTEGER,
    visit_purpose TEXT,
    notes TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
)
"""

TRIP_VISIT_BRIEFINGS_DDL = """
CREATE TABLE IF NOT EXISTS trip_visit_briefings (
    id TEXT PRIMARY KEY,
    stop_id TEXT NOT NULL UNIQUE REFERENCES trip_plan_stops(id),
    timezone TEXT,
    location_json TEXT NOT NULL DEFAULT '{}',
    customer_team_json TEXT NOT NULL DEFAULT '[]',
    contacts_json TEXT NOT NULL DEFAULT '[]',
    participants_json TEXT NOT NULL DEFAULT '[]',
    channel_partner_companions_json TEXT NOT NULL DEFAULT '[]',
    equipment_json TEXT NOT NULL DEFAULT '[]',
    agenda_items_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
)
"""

STOP_HALF_DAY_COLUMNS = {
    "duration_half_days": "INTEGER NOT NULL DEFAULT 2 CHECK (duration_half_days BETWEEN 1 AND 60)",
    "preferred_period": (
        "TEXT NOT NULL DEFAULT 'auto' CHECK (preferred_period IN ('auto','AM','PM'))"
    ),
    "planned_start_period": (
        "TEXT CHECK (planned_start_period IN ('AM','PM'))"
    ),
    "planned_end_period": "TEXT CHECK (planned_end_period IN ('AM','PM'))",
    "schedule_locked": (
        "INTEGER NOT NULL DEFAULT 0 CHECK (schedule_locked IN (0,1))"
    ),
    "confirmation_status": (
        "TEXT NOT NULL DEFAULT 'unconfirmed' CHECK (confirmation_status IN "
        "('unconfirmed','tentative','confirmed','needs_reconfirmation','cancelled'))"
    ),
}

LEG_HALF_DAY_COLUMNS = {
    "travel_half_days": (
        "INTEGER NOT NULL DEFAULT 0 CHECK (travel_half_days BETWEEN 0 AND 60)"
    ),
    "manual_travel_half_days": (
        "INTEGER CHECK (manual_travel_half_days BETWEEN 0 AND 60)"
    ),
    "planned_start_date": "TEXT",
    "planned_start_period": (
        "TEXT CHECK (planned_start_period IN ('AM','PM'))"
    ),
    "planned_end_date": "TEXT",
    "planned_end_period": "TEXT CHECK (planned_end_period IN ('AM','PM'))",
}


LEG_FLIGHT_AIRPORT_COLUMNS = {
    "departure_airport_name": "TEXT",
    "departure_airport_lat": (
        "REAL CHECK (departure_airport_lat BETWEEN -90 AND 90)"
    ),
    "departure_airport_lng": (
        "REAL CHECK (departure_airport_lng BETWEEN -180 AND 180)"
    ),
    "arrival_airport_name": "TEXT",
    "arrival_airport_lat": "REAL CHECK (arrival_airport_lat BETWEEN -90 AND 90)",
    "arrival_airport_lng": "REAL CHECK (arrival_airport_lng BETWEEN -180 AND 180)",
    # A traveller may reach a distant airport the night before, or rest near the
    # landing airport, so each end can hold its own stay.
    "departure_airport_stay_half_days": (
        "INTEGER NOT NULL DEFAULT 0 "
        "CHECK (departure_airport_stay_half_days BETWEEN 0 AND 60)"
    ),
    "arrival_airport_stay_half_days": (
        "INTEGER NOT NULL DEFAULT 0 "
        "CHECK (arrival_airport_stay_half_days BETWEEN 0 AND 60)"
    ),
}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def apply_trip_planning_schema_v4(conn: sqlite3.Connection) -> None:
    """Add v4 columns/table without rewriting any schema3 business rows."""
    existing = _column_names(conn, "trip_plans")
    priority_was_missing = "transport_mode_priority" not in existing
    for name, declaration in PLAN_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE trip_plans ADD COLUMN {name} {declaration}")
    if priority_was_missing:
        conn.execute(
            """
            UPDATE trip_plans
            SET transport_mode_priority = CASE travel_mode
                WHEN 'flight' THEN '["flight"]'
                WHEN 'drive' THEN '["drive"]'
                WHEN 'ground_public' THEN '["ground_public"]'
                WHEN 'other' THEN '["other"]'
                ELSE '["flight","drive","ground_public"]'
            END
            """
        )
    conn.execute(TRIP_PLAN_LEGS_DDL)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_legs_active_key "
        "ON trip_plan_legs(plan_id, leg_key) WHERE archived_at IS NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trip_legs_plan_sequence "
        "ON trip_plan_legs(plan_id, archived_at, sequence_no)"
    )


def apply_trip_planning_schema_v5(conn: sqlite3.Connection) -> None:
    """Add independent non-customer route stops and typed leg references."""
    conn.execute(TRIP_PLAN_FREE_STOPS_DDL)
    leg_columns = _column_names(conn, "trip_plan_legs")
    if "from_free_stop_id" not in leg_columns:
        conn.execute(
            "ALTER TABLE trip_plan_legs ADD COLUMN from_free_stop_id "
            "TEXT REFERENCES trip_plan_free_stops(id)"
        )
    if "to_free_stop_id" not in leg_columns:
        conn.execute(
            "ALTER TABLE trip_plan_legs ADD COLUMN to_free_stop_id "
            "TEXT REFERENCES trip_plan_free_stops(id)"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trip_free_stops_plan "
        "ON trip_plan_free_stops(plan_id, archived_at, sequence_no)"
    )


def _add_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> set[str]:
    """Append missing columns and return the names added by this invocation."""
    existing = _column_names(conn, table)
    added = set()
    for name, declaration in columns.items():
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        added.add(name)
    return added


def apply_trip_planning_schema_v6(conn: sqlite3.Connection) -> None:
    """Add half-day scheduling and visit briefing data without rebuilding old tables."""
    for table in ("trip_plan_stops", "trip_plan_free_stops"):
        added = _add_columns(conn, table, STOP_HALF_DAY_COLUMNS)
        if "duration_half_days" in added:
            conn.execute(
                f"""
                UPDATE {table}
                SET duration_half_days = MIN(60, MAX(1, COALESCE(stay_days, 1) * 2))
                """
            )
        if "planned_start_period" in added:
            conn.execute(
                f"UPDATE {table} SET planned_start_period = 'AM' "
                "WHERE planned_date IS NOT NULL"
            )
        if "planned_end_period" in added:
            conn.execute(
                f"UPDATE {table} SET planned_end_period = 'PM' "
                "WHERE planned_end_date IS NOT NULL OR planned_date IS NOT NULL"
            )

    leg_added = _add_columns(conn, "trip_plan_legs", LEG_HALF_DAY_COLUMNS)
    if "travel_half_days" in leg_added:
        conn.execute(
            """
            UPDATE trip_plan_legs
            SET travel_half_days = MIN(60, MAX(0, COALESCE(travel_days, 0) * 2))
            """
        )
    if "manual_travel_half_days" in leg_added:
        conn.execute(
            """
            UPDATE trip_plan_legs
            SET manual_travel_half_days = MIN(60, MAX(0, manual_travel_days * 2))
            WHERE manual_travel_days IS NOT NULL
            """
        )

    conn.execute(TRIP_VISIT_BRIEFINGS_DDL)
    _add_columns(
        conn,
        "trip_visit_briefings",
        {"channel_partner_companions_json": "TEXT NOT NULL DEFAULT '[]'"},
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_visit_briefings_stop "
        "ON trip_visit_briefings(stop_id)"
    )


def apply_trip_planning_schema_v7(conn: sqlite3.Connection) -> None:
    """Let a flown leg record the airports it departs from and arrives at.

    Airports belong to the connection between two stops, not to the stop list:
    stored as stops they would be reordered away from the leg they serve. Purely
    additive columns keep existing legs and itineraries untouched.
    """
    _add_columns(conn, "trip_plan_legs", LEG_FLIGHT_AIRPORT_COLUMNS)


def apply_trip_planning_schema_v8(conn: sqlite3.Connection) -> None:
    """Let a plan record who travels, and which member each leg belongs to.

    A trip is planned for team members, so a leg is one member's movement. Two
    colleagues can cover the same pair of stops by different transport, which
    the old ``(plan_id, leg_key)`` unique index could not represent.

    ``member_id`` holds a ``users.id``, not a ``trip_plan_members.id``: a leg
    records who travelled, and that has to stay readable after the team list is
    edited. It is NULL on a legacy single-path leg, so two partial unique
    indexes are needed - SQLite treats NULLs as distinct, and one combined index
    would stop protecting legacy plans from duplicate legs.
    """
    conn.execute(TRIP_PLAN_MEMBERS_DDL)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_plan_members_user "
        "ON trip_plan_members(plan_id, user_id)"
    )
    if "planning_mode" not in _column_names(conn, "trip_plans"):
        conn.execute(
            "ALTER TABLE trip_plans ADD COLUMN planning_mode TEXT NOT NULL "
            "DEFAULT 'legacy' CHECK (planning_mode IN ('legacy', 'team'))"
        )
    if "member_id" not in _column_names(conn, "trip_plan_legs"):
        conn.execute(
            "ALTER TABLE trip_plan_legs ADD COLUMN member_id TEXT "
            "REFERENCES users(id)"
        )
    # A stop that is not a customer visit can belong to the whole team or to
    # some of its members: NULL means everyone, so ordinary trips store nothing.
    if "participant_user_ids_json" not in _column_names(
        conn, "trip_plan_free_stops"
    ):
        conn.execute(
            "ALTER TABLE trip_plan_free_stops ADD COLUMN "
            "participant_user_ids_json TEXT"
        )
    conn.execute("DROP INDEX IF EXISTS idx_trip_legs_active_key")
    conn.execute("DROP INDEX IF EXISTS idx_trip_legs_active_member_key")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_legs_active_shared_key "
        "ON trip_plan_legs(plan_id, leg_key) "
        "WHERE archived_at IS NULL AND member_id IS NULL"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_legs_active_member_key "
        "ON trip_plan_legs(plan_id, member_id, leg_key) "
        "WHERE archived_at IS NULL AND member_id IS NOT NULL"
    )
