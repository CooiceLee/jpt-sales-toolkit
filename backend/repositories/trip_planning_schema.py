"""Append-only Trip Planner schema migrations."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone


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
    departure_date TEXT,
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


def apply_trip_planning_schema_v9(conn: sqlite3.Connection) -> None:
    """Record whether a planned time was accepted or merely calculated.

    A stop's planned time had two meanings at once: a time somebody chose to
    accept, and wherever the last calculation happened to put the visit. The
    calculation writes its result back, so its own output became an anchor for
    the next run: move the trip a week earlier and an unscheduled visit stayed
    on the date the first run gave it. This flag is the difference, and only a
    person's decision sets it.
    """
    for table in ("trip_plan_stops", "trip_plan_free_stops"):
        if "planned_time_accepted" not in _column_names(conn, table):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN planned_time_accepted "
                "INTEGER NOT NULL DEFAULT 0 "
                "CHECK (planned_time_accepted IN (0, 1))"
            )


def apply_trip_planning_schema_v10(conn: sqlite3.Connection) -> None:
    """Let a member leave on a day of their own.

    Schema 9 has shipped, so this cannot be folded into the step that created
    the team table: a database already at 9 would never run that step again. A
    member who joins the trip a week in has not been travelling for that week,
    and without a date of their own the plan flies everybody out on day one.
    """
    if "departure_date" not in _column_names(conn, "trip_plan_members"):
        conn.execute(
            "ALTER TABLE trip_plan_members ADD COLUMN departure_date TEXT"
        )


LEG_TRANSFER_COLUMNS = {
    "departure_transfer_half_days": (
        "INTEGER CHECK (departure_transfer_half_days BETWEEN 0 AND 60)"
    ),
    "arrival_transfer_half_days": (
        "INTEGER CHECK (arrival_transfer_half_days BETWEEN 0 AND 60)"
    ),
}


def apply_trip_planning_schema_v11(conn: sqlite3.Connection) -> None:
    """Let the drive to and from an airport carry a time somebody chose.

    A flown connection is three movements, and only the flight's own hours were
    ever askable. The transfers were left as estimates the reader could see were
    wrong and could not correct.
    """
    _add_columns(conn, "trip_plan_legs", LEG_TRANSFER_COLUMNS)


LEG_TRANSFER_DETAIL_COLUMNS = {
    "departure_transfer_mode": (
        "TEXT CHECK (departure_transfer_mode IN "
        "('drive', 'ground_public', 'other'))"
    ),
    "departure_transfer_time_hours": (
        "REAL CHECK (departure_transfer_time_hours >= 0)"
    ),
    "arrival_transfer_mode": (
        "TEXT CHECK (arrival_transfer_mode IN "
        "('drive', 'ground_public', 'other'))"
    ),
    "arrival_transfer_time_hours": (
        "REAL CHECK (arrival_transfer_time_hours >= 0)"
    ),
}


def apply_trip_planning_schema_v12(conn: sqlite3.Connection) -> None:
    """Let each airport transfer say how it is travelled and how long it takes.

    Schema 11 gave the drives a length in days. How they are made was still the
    plan's first ground mode for both ends at once, and the hours were always
    estimated - so a train to the airport and a taxi at the other end could not
    be described, and neither could a time the traveller already knows.
    """
    _add_columns(conn, "trip_plan_legs", LEG_TRANSFER_DETAIL_COLUMNS)


STOPS_TRISTATE_TABLE = "trip_plan_stops"
STOPS_REBUILD_TABLE = "trip_plan_stops_rebuild_v13"

# A stop can only be described honestly once "not answered" is a value of its
# own: a sample or a quote stored as 0 could never say whether somebody chose
# "no" or never filled it in. And what a visit was planned for is not what
# happened, so when it happened is recorded separately.
STOPS_TRISTATE_DDL = f"""
CREATE TABLE {STOPS_REBUILD_TABLE} (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    customer_id TEXT NOT NULL REFERENCES customers(id),
    lead_id TEXT REFERENCES leads(id),
    sequence_no INTEGER NOT NULL DEFAULT 1,
    planned_date TEXT,
    planned_end_date TEXT,
    stay_days INTEGER NOT NULL DEFAULT 1,
    duration_half_days INTEGER NOT NULL DEFAULT 2 CHECK (
        duration_half_days BETWEEN 1 AND 60
    ),
    preferred_period TEXT NOT NULL DEFAULT 'auto' CHECK (
        preferred_period IN ('auto', 'AM', 'PM')
    ),
    planned_start_period TEXT CHECK (planned_start_period IN ('AM', 'PM')),
    planned_end_period TEXT CHECK (planned_end_period IN ('AM', 'PM')),
    schedule_locked INTEGER NOT NULL DEFAULT 0 CHECK (schedule_locked IN (0, 1)),
    planned_time_accepted INTEGER NOT NULL DEFAULT 0 CHECK (planned_time_accepted IN (0, 1)),
    confirmation_status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK (
        confirmation_status IN (
            'unconfirmed', 'tentative', 'confirmed',
            'needs_reconfirmation', 'cancelled'
        )
    ),
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
    actual_visit_date TEXT,
    actual_visit_period TEXT CHECK (actual_visit_period IN ('AM', 'PM')),
    visit_customer_needs TEXT,
    visit_competitor TEXT,
    visit_budget TEXT,
    visit_decision_maker TEXT,
    visit_next_action TEXT,
    visit_followup_due_date TEXT,
    visit_sample_needed INTEGER CHECK (visit_sample_needed IN (0, 1)),
    visit_quote_needed INTEGER CHECK (visit_quote_needed IN (0, 1)),
    followup_activity_id TEXT REFERENCES lead_activities(id),
    result_activity_id TEXT REFERENCES lead_activities(id),
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
)
"""

STOPS_INDEX_DDL = (
    f"CREATE INDEX IF NOT EXISTS idx_trip_stops_plan "
    f"ON {STOPS_TRISTATE_TABLE}(plan_id, sequence_no)",
    f"CREATE INDEX IF NOT EXISTS idx_trip_stops_customer "
    f"ON {STOPS_TRISTATE_TABLE}(customer_id)",
    f"CREATE INDEX IF NOT EXISTS idx_trip_stops_lead "
    f"ON {STOPS_TRISTATE_TABLE}(lead_id)",
)

# Columns whose stored meaning changes, and what each row becomes. A stored 1
# was somebody ticking the box, so it stays. A stored 0 cannot be told apart
# from a box nobody touched, and claiming it means "no" would invent an answer.
STOPS_TRISTATE_TRANSFORMS = {
    "visit_sample_needed": "CASE WHEN visit_sample_needed = 1 THEN 1 END",
    "visit_quote_needed": "CASE WHEN visit_quote_needed = 1 THEN 1 END",
}

# Read back to prove the rebuild carried the rows, not merely the count.
STOPS_IDENTITY_COLUMNS = (
    "id", "plan_id", "customer_id", "lead_id", "sequence_no", "row_version",
    "result_status", "result_activity_id", "followup_activity_id",
    "archived_at", "created_at", "updated_at",
)


def _table_columns(conn: sqlite3.Connection, table: str) -> dict:
    return {row[1]: row for row in conn.execute(f"PRAGMA table_info({table})")}


def _stops_are_tristate(columns: dict) -> bool:
    """Whether this database already holds the schema 13 shape."""
    return (
        "actual_visit_date" in columns
        and "actual_visit_period" in columns
        and columns["visit_sample_needed"][3] == 0
        and columns["visit_quote_needed"][3] == 0
    )


def _stops_identity(conn: sqlite3.Connection, table: str) -> set:
    return set(
        conn.execute(
            f"SELECT {', '.join(STOPS_IDENTITY_COLUMNS)} FROM {table}"
        ).fetchall()
    )


def apply_trip_planning_schema_v13(conn: sqlite3.Connection) -> None:
    """Let a stop say a visit was not answered, and when it actually happened.

    SQLite cannot loosen NOT NULL in place, so the table is rebuilt. Every
    column is carried by name - a migrated database holds them in a different
    order than a fresh one - and the rows are read back and compared before the
    old table is let go. Anything that does not match raises, which rolls the
    whole startup migration back onto the backup taken before it. References
    are read back by ``validate_database_file`` after startup has committed
    every step, not before the commit.
    """
    existing = _table_columns(conn, STOPS_TRISTATE_TABLE)
    if not existing or _stops_are_tristate(existing):
        return

    conn.execute(f"DROP TABLE IF EXISTS {STOPS_REBUILD_TABLE}")
    conn.execute(STOPS_TRISTATE_DDL)
    rebuilt = _table_columns(conn, STOPS_REBUILD_TABLE)

    lost = set(existing) - set(rebuilt)
    if lost:
        raise RuntimeError(
            f"schema 13 would drop stored trip stop columns: {sorted(lost)}"
        )

    carried = [name for name in rebuilt if name in existing]
    values = [STOPS_TRISTATE_TRANSFORMS.get(name, name) for name in carried]
    before_count = conn.execute(
        f"SELECT COUNT(*) FROM {STOPS_TRISTATE_TABLE}"
    ).fetchone()[0]
    before_identity = _stops_identity(conn, STOPS_TRISTATE_TABLE)
    answered = conn.execute(
        f"SELECT COUNT(*) FROM {STOPS_TRISTATE_TABLE} "
        "WHERE visit_sample_needed = 1 OR visit_quote_needed = 1"
    ).fetchone()[0]

    conn.execute(
        f"INSERT INTO {STOPS_REBUILD_TABLE} ({', '.join(carried)}) "
        f"SELECT {', '.join(values)} FROM {STOPS_TRISTATE_TABLE}"
    )
    after_count = conn.execute(
        f"SELECT COUNT(*) FROM {STOPS_REBUILD_TABLE}"
    ).fetchone()[0]
    if after_count != before_count:
        raise RuntimeError(
            f"schema 13 copied {after_count} of {before_count} trip stops"
        )
    if _stops_identity(conn, STOPS_REBUILD_TABLE) != before_identity:
        raise RuntimeError("schema 13 changed trip stop identities or ownership")
    kept = conn.execute(
        f"SELECT COUNT(*) FROM {STOPS_REBUILD_TABLE} "
        "WHERE visit_sample_needed = 1 OR visit_quote_needed = 1"
    ).fetchone()[0]
    if kept != answered:
        raise RuntimeError(
            f"schema 13 kept {kept} of {answered} answered sample or quote flags"
        )

    # The children point at the table by name, so the new one has to carry the
    # name once the old one is gone. Reference enforcement is off for the whole
    # startup migration; startup reads the finished database back afterwards
    # and restores the backup if anything is left pointing at nothing.
    conn.execute(f"DROP TABLE {STOPS_TRISTATE_TABLE}")
    conn.execute(
        f"ALTER TABLE {STOPS_REBUILD_TABLE} RENAME TO {STOPS_TRISTATE_TABLE}"
    )
    for statement in STOPS_INDEX_DDL:
        conn.execute(statement)


TRIP_WORKING_EXPORTS_DDL = """
CREATE TABLE IF NOT EXISTS trip_working_exports (
    workbook_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    format TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    last_imported_at TEXT,
    last_imported_by TEXT REFERENCES users(id)
)
"""

TRIP_WORKING_EXPORT_ROWS_DDL = """
CREATE TABLE IF NOT EXISTS trip_working_export_rows (
    workbook_id TEXT NOT NULL REFERENCES trip_working_exports(workbook_id),
    row_token TEXT NOT NULL,
    stop_id TEXT NOT NULL REFERENCES trip_plan_stops(id),
    row_version INTEGER NOT NULL,
    baseline_json TEXT NOT NULL,
    PRIMARY KEY (workbook_id, row_token)
)
"""

TRIP_WORKING_EXPORT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_trip_working_exports_plan "
    "ON trip_working_exports(plan_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_trip_working_export_rows_token "
    "ON trip_working_export_rows(row_token)",
)


def apply_trip_planning_schema_v14(conn: sqlite3.Connection) -> None:
    """Record what each field workbook was issued with, on this machine.

    A returned workbook cannot vouch for itself: whoever holds the file can
    unprotect its hidden sheet and rewrite which visit a row is about, or the
    values it was exported with, and an import that trusted them would file a
    result against another customer or hide a real conflict. So the issuing
    installation keeps the list, and the file carries only its own identifier
    and one token per row.
    """
    conn.execute(TRIP_WORKING_EXPORTS_DDL)
    conn.execute(TRIP_WORKING_EXPORT_ROWS_DDL)
    for statement in TRIP_WORKING_EXPORT_INDEXES:
        conn.execute(statement)


def apply_trip_planning_schema_v15(conn: sqlite3.Connection) -> None:
    """Make every trip a team trip, with at least the person who owns it.

    Two ways to plan the same journey meant two of everything to keep in step:
    two sets of controls, two schedulers, two shapes of export, and a reader
    who had to know which one they were looking at before anything on screen
    meant what it said. A trip with one traveller is a team of one, so that is
    what it becomes - and the owner is that one traveller, because the engine
    needs somebody to move and a trip with nobody on it plans nothing.

    Anyone already on the trip is left exactly as they are.
    """
    conn.execute(
        "UPDATE trip_plans SET planning_mode = 'team' WHERE planning_mode != 'team'"
    )
    stamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    lonely = conn.execute(
        """
        SELECT p.id, p.owner_id, p.created_by
        FROM trip_plans p
        WHERE NOT EXISTS (
            SELECT 1 FROM trip_plan_members m WHERE m.plan_id = p.id
        )
        """
    ).fetchall()
    for plan in lonely:
        traveller = plan["owner_id"] or plan["created_by"]
        if not traveller:
            # Nothing to name as the traveller. Left for the reader to add,
            # rather than inventing one.
            continue
        conn.execute(
            "INSERT INTO trip_plan_members (id, plan_id, user_id, created_at, "
            "created_by, updated_at, updated_by, row_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (str(uuid.uuid4()), plan["id"], traveller, stamp, traveller,
             stamp, traveller),
        )
