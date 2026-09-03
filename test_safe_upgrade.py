"""Regression coverage for fail-safe upgrades from supported desktop data."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.config import APP_VERSION, init_settings
from backend.repositories import APP_SCHEMA_VERSION, close_db, read_app_schema_version
from backend.repositories import base
from backend.repositories.base import APP_SCHEMA_MIGRATIONS
from backend.services.admin_service import AdminService
from backend.startup_upgrade import initialize_database_safely


ROOT = Path(__file__).parent
CORE_TABLES = (
    "users",
    "user_credentials",
    "customers",
    "leads",
    "lead_assignments",
    "lead_activities",
    "pre_sales_tasks",
    "after_sales_tasks",
    "attachments",
    "device_authorizations",
    "trip_plans",
    "trip_plan_stops",
)
NOW = "2026-07-01T00:00:00"
V0118_SCHEMA_VERSION = 3
DEVELOPMENT_CURRENT_SCHEMA_FIXTURE = "development-current-schema"
SCHEMA3_RELEASE_VERSIONS = {"0.11.8-internal", "0.11.9-internal"}


def _remove_post_schema3_trip_schema(conn: sqlite3.Connection) -> None:
    """Turn the canonical schema into the exact released schema-3 Trip shape."""
    conn.execute("DROP TABLE IF EXISTS trip_visit_briefings")
    conn.execute("DROP TABLE IF EXISTS trip_plan_legs")
    conn.execute("DROP TABLE IF EXISTS trip_plan_free_stops")
    existing = {row[1] for row in conn.execute("PRAGMA table_info(trip_plans)")}
    for column in (
        "route_order_mode",
        "transport_mode_priority",
        "departure_window_start",
        "departure_window_end",
        "return_window_start",
        "return_window_end",
    ):
        if column in existing:
            conn.execute(f"ALTER TABLE trip_plans DROP COLUMN {column}")
    stop_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(trip_plan_stops)")
    }
    for column in (
        "duration_half_days",
        "preferred_period",
        "planned_start_period",
        "planned_end_period",
        "schedule_locked",
        "confirmation_status",
    ):
        if column in stop_columns:
            conn.execute(f"ALTER TABLE trip_plan_stops DROP COLUMN {column}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in CORE_TABLES
        }
    finally:
        conn.close()


def _authorization_state(db_path: Path) -> dict[str, list[tuple]]:
    """Capture security-sensitive rows that an application upgrade must preserve."""
    conn = sqlite3.connect(str(db_path))
    try:
        return {
            "organizations": conn.execute(
                "SELECT id, name, slug, authorization_provider, "
                "authorization_duration_days, is_active FROM organizations ORDER BY id"
            ).fetchall(),
            "users": conn.execute(
                "SELECT id, username, password_hash, display_name, role, region, is_active "
                "FROM users ORDER BY id"
            ).fetchall(),
            "credentials": conn.execute(
                "SELECT id, organization_id, user_id, password_hash, password_scheme, "
                "must_change_password, is_active FROM user_credentials ORDER BY id"
            ).fetchall(),
            "device_authorizations": conn.execute(
                "SELECT id, organization_id, user_id, device_fingerprint_hash, role, "
                "activation_state, authorization_version, payload_json, signature, "
                "signature_algorithm, signing_key_id, issued_at, valid_from, expires_at, "
                "is_active, created_by FROM device_authorizations ORDER BY id"
            ).fetchall(),
        }
    finally:
        conn.close()


def _schema_ledger(db_path: Path) -> list[tuple]:
    """Capture the audited application-schema ledger without normalizing it."""
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT version, name, app_version, applied_at "
            "FROM app_schema_migrations ORDER BY version"
        ).fetchall()
    finally:
        conn.close()


def _tech_exchange_state(db_path: Path) -> dict[str, list[tuple]]:
    """Capture released task-package state that an upgrade must retain."""
    conn = sqlite3.connect(str(db_path))
    try:
        return {
            "batches": conn.execute(
                "SELECT package_id, package_type, direction, organization_id, "
                "source_user_id, recipient_user_id, parent_package_id, payload_sha256, "
                "manifest_json, status, created_at, imported_at, imported_by "
                "FROM tech_task_exchange_batches ORDER BY package_id"
            ).fetchall(),
            "bindings": conn.execute(
                "SELECT id, organization_id, task_type, source_task_id, local_task_id, "
                "source_lead_id, local_lead_id, source_customer_id, local_customer_id, "
                "leader_user_id, tech_user_id, source_row_version, source_snapshot_json, "
                "source_package_id, local_row_version_at_sync, "
                "last_exported_local_row_version, last_exported_result_snapshot_json, "
                "is_active, created_at, updated_at "
                "FROM tech_task_exchange_bindings ORDER BY id"
            ).fetchall(),
        }
    finally:
        conn.close()


def _trip_planner_state(db_path: Path) -> dict[str, list[tuple]]:
    """Capture route rows that existed in the v0.11.9 schema-3 release."""
    conn = sqlite3.connect(str(db_path))
    try:
        return {
            "plans": conn.execute(
                "SELECT id, title, description, owner_id, region, start_date, end_date, "
                "origin_name, destination_name, travel_mode, avoid_weekends, status, "
                "row_version FROM trip_plans ORDER BY id"
            ).fetchall(),
            "stops": conn.execute(
                "SELECT id, plan_id, lead_id, customer_id, sequence_no, planned_date, "
                "planned_end_date, stay_days, travel_mode, travel_distance_km, "
                "travel_time_hours, travel_days, result_status, row_version "
                "FROM trip_plan_stops ORDER BY id"
            ).fetchall(),
        }
    finally:
        conn.close()


def _assert_migrated_trip_state(
    db_path: Path,
    expected_legacy_state: dict[str, list[tuple]],
) -> None:
    """Verify schema-3 route rows and their schema-6 backfill values."""
    assert _trip_planner_state(db_path) == expected_legacy_state
    conn = sqlite3.connect(str(db_path))
    try:
        plan = conn.execute(
            "SELECT route_order_mode, transport_mode_priority, "
            "departure_window_start, departure_window_end, "
            "return_window_start, return_window_end "
            "FROM trip_plans WHERE id = 'trip-plan-1'"
        ).fetchone()
        assert plan is not None
        assert plan[0] == "auto"
        assert json.loads(plan[1]) == ["drive"]
        assert plan[2:] == (None, None, None, None)

        stop = conn.execute(
            "SELECT duration_half_days, preferred_period, planned_start_period, "
            "planned_end_period, schedule_locked, confirmation_status "
            "FROM trip_plan_stops WHERE id = 'trip-stop-1'"
        ).fetchone()
        assert stop == (4, "auto", "AM", "PM", 0, "unconfirmed")
        assert conn.execute("SELECT COUNT(*) FROM trip_plan_legs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM trip_plan_free_stops").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM trip_visit_briefings").fetchone()[0] == 0
        briefing_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(trip_visit_briefings)")
        }
        assert "channel_partner_companions_json" in briefing_columns
    finally:
        conn.close()


def _seed_fixture(data_dir: Path, source_version: str) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "database.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript((ROOT / "backend" / "schema.sql").read_text(encoding="utf-8"))
        is_schema3_release = source_version in SCHEMA3_RELEASE_VERSIONS
        is_v0119_schema = source_version == "0.11.9-internal"
        is_current_schema = source_version == DEVELOPMENT_CURRENT_SCHEMA_FIXTURE
        has_tech_exchange = is_schema3_release or is_current_schema
        # Legacy source fixtures predate the v2 task-exchange tables even
        # though the current canonical schema contains them. Released schema-3
        # fixtures deliberately retain the real task-exchange tables and ledger.
        if not has_tech_exchange:
            conn.execute("DROP TABLE IF EXISTS tech_task_exchange_bindings")
            conn.execute("DROP TABLE IF EXISTS tech_task_exchange_batches")
        if is_schema3_release:
            _remove_post_schema3_trip_schema(conn)
        source_schema_version = (
            APP_SCHEMA_VERSION
            if is_current_schema
            else V0118_SCHEMA_VERSION
            if is_schema3_release
            else (1 if source_version == "0.11.7-internal" else 0)
        )
        if source_schema_version == 1:
            conn.execute(
                "INSERT INTO app_schema_migrations "
                "(version, name, app_version, applied_at) VALUES (1, ?, ?, ?)",
                ("runtime_schema_v1", source_version, NOW),
            )
            conn.execute("PRAGMA user_version = 1")
        elif has_tech_exchange:
            ledger_app_versions = {
                1: "0.11.7-internal",
                2: "0.11.8-internal",
                3: "0.11.8-internal",
                4: APP_VERSION,
                5: APP_VERSION,
                6: APP_VERSION,
                7: APP_VERSION,
                8: APP_VERSION,
                9: APP_VERSION,
                10: APP_VERSION,
                11: APP_VERSION,
                12: APP_VERSION,
                13: APP_VERSION,
                14: APP_VERSION,
            }
            conn.executemany(
                "INSERT INTO app_schema_migrations "
                "(version, name, app_version, applied_at) VALUES (?, ?, ?, ?)",
                [
                    (version, name, ledger_app_versions[version], NOW)
                    for version, name in APP_SCHEMA_MIGRATIONS
                    if version <= source_schema_version
                ],
            )
            conn.execute(f"PRAGMA user_version = {source_schema_version}")
        if source_version == "0.11.3-internal":
            conn.execute("DROP INDEX IF EXISTS idx_pre_sales_client_request")
            conn.execute("ALTER TABLE pre_sales_tasks DROP COLUMN client_request_id")
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, 1, ?, NULL)",
            ("user-1", "fixture.leader", "hash", "Fixture Leader", "leader", "GLOBAL", NOW),
        )
        if has_tech_exchange:
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, 1, ?, NULL)",
                ("user-2", "fixture.tech", "tech-hash", "Fixture Tech", "tech", "GLOBAL", NOW),
            )
        conn.execute(
            "INSERT INTO user_credentials "
            "(id, organization_id, user_id, password_hash, password_scheme, "
            "must_change_password, is_active, created_at, updated_at) "
            "VALUES ('credential-1', ?, 'user-1', 'hash', 'legacy_sha256', 0, 1, ?, ?)",
            ("00000000-0000-0000-0000-000000000001", NOW, NOW),
        )
        if has_tech_exchange:
            conn.execute(
                "INSERT INTO user_credentials "
                "(id, organization_id, user_id, password_hash, password_scheme, "
                "must_change_password, is_active, created_at, updated_at) "
                "VALUES ('credential-2', ?, 'user-2', 'tech-hash', 'legacy_sha256', "
                "0, 1, ?, ?)",
                ("00000000-0000-0000-0000-000000000001", NOW, NOW),
            )
        conn.execute(
            "INSERT INTO customers "
            "(id, display_name, normalized_name, country, city, address, region, "
            "created_at, created_by, updated_at, updated_by, row_version) "
            "VALUES ('customer-1', 'Fixture Customer', 'fixture customer', 'DE', "
            "'Berlin', 'Fixture Street 1', 'Europe', ?, 'user-1', ?, 'user-1', 1)",
            (NOW, NOW),
        )
        conn.execute(
            "INSERT INTO leads "
            "(id, display_id, customer_id, title, owner_id, sales_stage, "
            "fulfillment_status, service_status, created_at, created_by, updated_at, "
            "updated_by, row_version) VALUES "
            "('lead-1', 'JPT-FIXTURE-1', 'customer-1', 'Upgrade fixture', 'user-1', "
            "'Following', 'Not Started', 'None', ?, 'user-1', ?, 'user-1', 1)",
            (NOW, NOW),
        )
        conn.execute(
            "INSERT INTO lead_assignments "
            "(id, lead_id, user_id, assignment_type, created_at, created_by) "
            "VALUES ('assignment-1', 'lead-1', 'user-1', 'owner', ?, 'user-1')",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO lead_activities "
            "(id, lead_id, actor_id, action_type, visibility, is_formal_follow_up, "
            "summary, created_at) VALUES "
            "('activity-1', 'lead-1', 'user-1', 'comment', 'all', 0, "
            "'preserve me', ?)",
            (NOW,),
        )
        task_assignee = "user-2" if has_tech_exchange else "user-1"
        conn.execute(
            "INSERT INTO pre_sales_tasks "
            "(id, lead_id, assignee_id, status, request_json, created_at, created_by, "
            "updated_at, updated_by, row_version) VALUES "
            "('pre-task-1', 'lead-1', ?, 'Completed', '{}', ?, 'user-1', "
            "?, 'user-1', 1)",
            (task_assignee, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO after_sales_tasks "
            "(id, lead_id, assignee_id, issue_type, status, issue_description, "
            "created_at, created_by, updated_at, updated_by, row_version) VALUES "
            "('after-task-1', 'lead-1', ?, 'Other', 'Closed', 'fixture', "
            "?, 'user-1', ?, 'user-1', 1)",
            (task_assignee, NOW, NOW),
        )
        attachment_bytes = f"attachment-{source_version}".encode()
        attachment_sha = hashlib.sha256(attachment_bytes).hexdigest()
        conn.execute(
            "INSERT INTO attachments "
            "(id, lead_id, category, version_no, stored_name, original_name, mime_type, "
            "size_bytes, sha256, uploaded_by, uploaded_at) VALUES "
            "('attachment-1', 'lead-1', 'other', 1, 'fixture.txt', 'fixture.txt', "
            "'text/plain', ?, ?, 'user-1', ?)",
            (len(attachment_bytes), attachment_sha, NOW),
        )
        conn.execute(
            "INSERT INTO device_authorizations "
            "(id, organization_id, user_id, device_fingerprint_hash, role, "
            "activation_state, authorization_version, payload_json, signature, "
            "signature_algorithm, signing_key_id, issued_at, valid_from, expires_at, "
            "is_active, created_by, updated_at) VALUES "
            "('device-1', ?, 'user-1', 'fixture-device', 'leader', 'activated', 1, "
            "'{}', 'signature', 'ed25519', 'fixture-key', ?, ?, "
            "'2027-07-01T00:00:00', 1, 'user-1', ?)",
            ("00000000-0000-0000-0000-000000000001", NOW, NOW, NOW),
        )
        if has_tech_exchange:
            conn.execute(
                "INSERT INTO device_authorizations "
                "(id, organization_id, user_id, device_fingerprint_hash, role, "
                "activation_state, authorization_version, payload_json, signature, "
                "signature_algorithm, signing_key_id, issued_at, valid_from, expires_at, "
                "is_active, created_by, updated_at) VALUES "
                "('device-2', ?, 'user-2', 'fixture-tech-device', 'tech', 'activated', 1, "
                "'{}', 'tech-signature', 'ed25519', 'fixture-key', ?, ?, "
                "'2027-07-01T00:00:00', 1, 'user-1', ?)",
                ("00000000-0000-0000-0000-000000000001", NOW, NOW, NOW),
            )
            conn.execute(
                "INSERT INTO tech_task_exchange_batches "
                "(package_id, package_type, direction, organization_id, source_user_id, "
                "recipient_user_id, parent_package_id, payload_sha256, manifest_json, "
                "status, created_at, imported_at, imported_by) VALUES "
                "('assignment-batch-1', 'tech_task_assignment', 'leader_to_tech', ?, "
                "'user-1', 'user-2', NULL, ?, '{}', 'imported', ?, ?, 'user-2')",
                (
                    "00000000-0000-0000-0000-000000000001",
                    "a" * 64,
                    NOW,
                    NOW,
                ),
            )
            conn.execute(
                "INSERT INTO tech_task_exchange_bindings "
                "(id, organization_id, task_type, source_task_id, local_task_id, "
                "source_lead_id, local_lead_id, source_customer_id, local_customer_id, "
                "leader_user_id, tech_user_id, source_row_version, source_snapshot_json, "
                "source_package_id, local_row_version_at_sync, "
                "last_exported_local_row_version, last_exported_result_snapshot_json, "
                "is_active, created_at, updated_at) VALUES "
                "('binding-1', ?, 'pre_sales', 'source-pre-task-1', 'pre-task-1', "
                "'source-lead-1', 'lead-1', 'source-customer-1', 'customer-1', "
                "'user-1', 'user-2', 1, '{}', 'assignment-batch-1', 1, 1, "
                "'{\"status\":\"Completed\"}', 1, ?, ?)",
                ("00000000-0000-0000-0000-000000000001", NOW, NOW),
            )
        if is_v0119_schema:
            conn.execute(
                "INSERT INTO trip_plans "
                "(id, title, description, owner_id, region, start_date, end_date, "
                "origin_name, origin_lat, origin_lng, destination_name, destination_lat, "
                "destination_lng, travel_mode, avoid_weekends, holiday_dates, "
                "itinerary_generated_at, itinerary_summary, status, created_at, "
                "created_by, updated_at, updated_by, row_version) VALUES "
                "('trip-plan-1', 'Existing Europe trip', 'Preserve this route', "
                "'user-1', 'Europe', '2026-09-15', '2026-09-30', 'Shanghai Pudong', "
                "31.1443, 121.8083, 'Shanghai Pudong', 31.1443, 121.8083, 'drive', 1, "
                "'[]', '2026-08-18T00:00:00', 'Existing itinerary', 'Draft', ?, "
                "'user-1', ?, 'user-1', 7)",
                (NOW, NOW),
            )
            conn.execute(
                "INSERT INTO trip_plan_stops "
                "(id, plan_id, lead_id, customer_id, sequence_no, planned_date, "
                "planned_end_date, stay_days, travel_from_label, "
                "travel_mode, travel_distance_km, travel_time_hours, travel_days, "
                "result_status, created_at, created_by, updated_at, updated_by, "
                "row_version) VALUES "
                "('trip-stop-1', 'trip-plan-1', 'lead-1', 'customer-1', 1, "
                "'2026-09-18', '2026-09-19', 2, "
                "'Shanghai Pudong', 'drive', 545.0, 6.0, 1, 'Planned', ?, "
                "'user-1', ?, 'user-1', 5)",
                (NOW, NOW),
            )
        conn.commit()
    finally:
        conn.close()

    attachments = data_dir / "attachments"
    attachments.mkdir()
    attachment_path = attachments / "fixture.txt"
    attachment_path.write_bytes(attachment_bytes)
    config = data_dir / "config"
    config.mkdir()
    config_path = config / "authorization_issuer.pem"
    config_path.write_text(f"issuer-{source_version}", encoding="utf-8")
    (config / "desktop.lock").write_text("transient", encoding="utf-8")
    (config / "desktop_instance.json").write_text('{"port":8765}', encoding="utf-8")
    return {
        "counts": _counts(db_path),
        "authorization_state": _authorization_state(db_path),
        "schema_ledger": _schema_ledger(db_path),
        "tech_exchange_state": _tech_exchange_state(db_path) if has_tech_exchange else None,
        "trip_planner_state": _trip_planner_state(db_path) if is_v0119_schema else None,
        "source_schema_version": source_schema_version,
        "attachment_sha": _sha256(attachment_path),
        "config_sha": _sha256(config_path),
    }


# Every schema an installed release could be sitting on. 0.11.9 shipped schema 3,
# 0.12.0 shipped schema 6 and 0.12.1 shipped schema 9; 7, 8 and 10 to 13 were
# reached on the way and are covered so a later migration cannot skip them.
# 0.13.1 ships schema 14.
INTERMEDIATE_SCHEMA_BASELINES = (6, 7, 8, 9, 10, 11, 12, 13)

# What each migration added, so a fixture can be wound back to an earlier shape.
_SCHEMA_ADDITIONS = {
    7: (
        ("trip_plan_legs", (
            "departure_airport_name", "departure_airport_lat",
            "departure_airport_lng", "departure_airport_stay_half_days",
            "arrival_airport_name", "arrival_airport_lat",
            "arrival_airport_lng", "arrival_airport_stay_half_days",
        )),
    ),
    8: (
        ("trip_plan_legs", ("member_id",)),
        ("trip_plan_free_stops", ("participant_user_ids_json",)),
        ("trip_plans", ("planning_mode",)),
    ),
    9: (
        ("trip_plan_stops", ("planned_time_accepted",)),
        ("trip_plan_free_stops", ("planned_time_accepted",)),
    ),
    10: (
        ("trip_plan_members", ("departure_date",)),
    ),
    11: (
        ("trip_plan_legs", ("departure_transfer_half_days",
                            "arrival_transfer_half_days")),
    ),
    12: (
        ("trip_plan_legs", ("departure_transfer_mode",
                            "departure_transfer_time_hours",
                            "arrival_transfer_mode",
                            "arrival_transfer_time_hours")),
    ),
    13: (
        ("trip_plan_stops", ("actual_visit_date", "actual_visit_period")),
    ),
    14: (),
}

# The shape a stop had before schema 13, so a fixture can be a real pre-13
# database: the two answers were stored as a plain 0 or 1 that could not say
# "not answered", which is what the migration has to undo.
_TRIP_PLAN_STOPS_SCHEMA12_DDL = """
CREATE TABLE trip_plan_stops_schema12 (
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
    visit_customer_needs TEXT,
    visit_competitor TEXT,
    visit_budget TEXT,
    visit_decision_maker TEXT,
    visit_next_action TEXT,
    visit_followup_due_date TEXT,
    visit_sample_needed INTEGER NOT NULL DEFAULT 0 CHECK (
        visit_sample_needed IN (0, 1)
    ),
    visit_quote_needed INTEGER NOT NULL DEFAULT 0 CHECK (
        visit_quote_needed IN (0, 1)
    ),
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


def _restore_schema12_stops(conn: sqlite3.Connection) -> None:
    """Put the trip stop table back into its pre-13 shape."""
    # Reference enforcement can only be turned off outside a transaction, and
    # seeding the fixture opened one.
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(_TRIP_PLAN_STOPS_SCHEMA12_DDL)
    carried = [
        row[1] for row in conn.execute("PRAGMA table_info(trip_plan_stops_schema12)")
    ]
    values = [
        f"COALESCE({name}, 0)"
        if name in ("visit_sample_needed", "visit_quote_needed") else name
        for name in carried
    ]
    conn.execute(
        f"INSERT INTO trip_plan_stops_schema12 ({', '.join(carried)}) "
        f"SELECT {', '.join(values)} FROM trip_plan_stops"
    )
    conn.execute("DROP TABLE trip_plan_stops")
    conn.execute("ALTER TABLE trip_plan_stops_schema12 RENAME TO trip_plan_stops")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trip_stops_plan "
        "ON trip_plan_stops(plan_id, sequence_no)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trip_stops_customer "
        "ON trip_plan_stops(customer_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trip_stops_lead ON trip_plan_stops(lead_id)"
    )


def _wind_back_to_schema(conn: sqlite3.Connection, target: int) -> None:
    """Turn the canonical schema into the shape it had at an earlier version."""
    for version in sorted(_SCHEMA_ADDITIONS, reverse=True):
        if version <= target:
            continue
        if version == 14:
            # The manifest tables belong to schema 14 and nothing before it.
            conn.execute("DROP TABLE IF EXISTS trip_working_export_rows")
            conn.execute("DROP TABLE IF EXISTS trip_working_exports")
        if version == 13:
            # Losing NOT NULL is not a dropped column, so the table is rebuilt.
            _restore_schema12_stops(conn)
        if version == 8:
            # The partial indexes name member_id, so they go before the column.
            conn.execute("DROP INDEX IF EXISTS idx_trip_legs_active_member_key")
            conn.execute("DROP INDEX IF EXISTS idx_trip_legs_active_shared_key")
            conn.execute("DROP TABLE IF EXISTS trip_plan_members")
        for table, columns in _SCHEMA_ADDITIONS[version]:
            # schema.sql is not the whole of the current schema: some columns
            # exist only in the runtime migrations, so a fixture built from it
            # may already lack what this step would remove.
            present = {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            for column in columns:
                if column in present:
                    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    conn.execute(
        "DELETE FROM app_schema_migrations WHERE version > ?", (target,)
    )


def test_intermediate_schema_upgrade(baseline: int) -> None:
    """A database on an intermediate schema reaches the current one intact."""
    close_db()
    with tempfile.TemporaryDirectory(prefix=f"jpt_schema{baseline}_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        data_dir.mkdir(parents=True)
        db_path = data_dir / "database.sqlite"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(
                (ROOT / "backend" / "schema.sql").read_text(encoding="utf-8")
            )
            conn.executemany(
                "INSERT INTO app_schema_migrations "
                "(version, name, app_version, applied_at) VALUES (?, ?, ?, ?)",
                [(version, name, APP_VERSION, NOW)
                 for version, name in APP_SCHEMA_MIGRATIONS],
            )
            stamp = "2026-08-01T00:00:00Z"
            actor = "user-baseline"
            conn.execute(
                "INSERT INTO users (id,username,display_name,role,"
                "password_hash,is_active,created_at) VALUES "
                "(?,'baseline','Baseline','leader','h',1,?)", (actor, stamp))
            conn.execute(
                "INSERT INTO customers (id,display_name,normalized_name,lat,"
                "lng,created_at,updated_at,row_version) VALUES "
                "('cust-b','Baseline GmbH','baseline gmbh',50.1,8.7,?,?,1)",
                (stamp, stamp))
            conn.execute(
                "INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,"
                "status,created_at,created_by,updated_at,updated_by,row_version)"
                " VALUES ('plan-b','Baseline trip',?,'2026-09-14','2026-09-30',"
                "'Draft',?,?,?,?,1)", (actor, stamp, actor, stamp, actor))
            conn.execute(
                "INSERT INTO trip_plan_stops (id,plan_id,customer_id,"
                "sequence_no,created_at,created_by,updated_at,updated_by,"
                "row_version) VALUES ('stop-b','plan-b','cust-b',1,?,?,?,?,1)",
                (stamp, actor, stamp, actor))
            conn.execute(
                "INSERT INTO trip_plan_legs (id,plan_id,leg_key,sequence_no,"
                "from_kind,from_stop_id,to_kind,selected_mode,created_at,"
                "created_by,updated_at,updated_by,row_version) VALUES "
                "('leg-b','plan-b','stop-b>destination',1,'stop','stop-b',"
                "'destination','drive',?,?,?,?,1)",
                (stamp, actor, stamp, actor))
            conn.execute(
                "INSERT INTO trip_visit_briefings (id,stop_id,created_at,"
                "created_by,updated_at,updated_by,row_version) VALUES "
                "('brief-b','stop-b',?,?,?,?,1)", (stamp, actor, stamp, actor))
            _wind_back_to_schema(conn, baseline)
            # One answer somebody gave and one nobody could have given: before
            # schema 13 an untouched box and a deliberate "no" were both 0.
            conn.execute(
                "UPDATE trip_plan_stops SET visit_sample_needed = 1, "
                "visit_quote_needed = 0 WHERE id = 'stop-b'"
            )
            conn.commit()
        finally:
            conn.close()

        settings = init_settings(Path(temp_dir) / "app")
        settings.data_dir = data_dir
        settings.db_path = db_path
        settings.upload_dir = data_dir / "attachments"
        settings.backup_dir = data_dir / "backups"
        settings.runtime_config_dir = data_dir / "config"
        settings.backup_dir.mkdir()

        result = initialize_database_safely(settings)
        assert result.migrated is True, baseline
        assert result.source_schema_version == baseline, (
            result.source_schema_version, baseline
        )
        assert result.target_schema_version == APP_SCHEMA_VERSION
        assert result.backup_path, "an upgrade must be backed up before it runs"
        _assert_integrity(db_path)

        conn = sqlite3.connect(str(db_path))
        try:
            assert conn.execute(
                "SELECT display_name FROM customers"
            ).fetchone()[0] == "Baseline GmbH"
            assert conn.execute(
                "SELECT title FROM trip_plans"
            ).fetchone()[0] == "Baseline trip"
            # The columns this release depends on exist with their safe default.
            assert conn.execute(
                "SELECT planning_mode FROM trip_plans"
            ).fetchone()[0] == "legacy"
            assert conn.execute(
                "SELECT planned_time_accepted FROM trip_plan_stops"
            ).fetchone()[0] == 0
            # Whatever pointed at the stop still does after the table it lives
            # in was rebuilt.
            assert conn.execute(
                "SELECT from_stop_id FROM trip_plan_legs"
            ).fetchone()[0] == "stop-b"
            assert conn.execute(
                "SELECT stop_id FROM trip_visit_briefings"
            ).fetchone()[0] == "stop-b"
            # Schema 13 keeps the answer that was given and stops claiming one
            # that was not, and it does not invent a date the visit happened on.
            sample, quote, actual_date, actual_period = conn.execute(
                "SELECT visit_sample_needed, visit_quote_needed, "
                "actual_visit_date, actual_visit_period FROM trip_plan_stops"
            ).fetchone()
            assert sample == 1, f"a given answer was lost: {sample!r}"
            if baseline < 13:
                # Before schema 13 a 0 could not say whether anyone answered.
                assert quote is None, (
                    f"an untouched box was upgraded into a deliberate no: {quote!r}"
                )
            else:
                # From schema 13 on, a stored 0 is somebody answering "no".
                assert quote == 0, f"a deliberate no was lost: {quote!r}"
            assert actual_date is None and actual_period is None, (
                "the planned date was written in as the date the visit happened: "
                f"{actual_date!r} {actual_period!r}"
            )
        finally:
            conn.close()

        second = initialize_database_safely(settings)
        assert second.migrated is False, f"{baseline} migrated twice"
        assert len(list(settings.backup_dir.glob("pre_upgrade_*.zip"))) == 1
        print(f"PASS: schema-{baseline} upgrade fixture")


def test_current_schema_fixture() -> None:
    """A current development profile starts unchanged and without a backup."""
    assert APP_SCHEMA_VERSION == 14
    close_db()
    with tempfile.TemporaryDirectory(prefix="jpt_current_schema_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        expected = _seed_fixture(data_dir, DEVELOPMENT_CURRENT_SCHEMA_FIXTURE)
        settings = init_settings(Path(temp_dir) / "app")
        settings.data_dir = data_dir
        settings.db_path = data_dir / "database.sqlite"
        settings.upload_dir = data_dir / "attachments"
        settings.backup_dir = data_dir / "backups"
        settings.runtime_config_dir = data_dir / "config"
        settings.backup_dir.mkdir()

        before_hash = _sha256(settings.db_path)
        result = initialize_database_safely(settings)
        assert result.migrated is False
        assert result.source_schema_version == APP_SCHEMA_VERSION
        assert result.target_schema_version == APP_SCHEMA_VERSION
        assert result.backup_path is None
        assert not list(settings.backup_dir.glob("pre_upgrade_*.zip"))
        assert _sha256(settings.db_path) == before_hash
        assert _counts(settings.db_path) == expected["counts"]
        assert _authorization_state(settings.db_path) == expected["authorization_state"]
        assert _schema_ledger(settings.db_path) == expected["schema_ledger"]
        assert _tech_exchange_state(settings.db_path) == expected["tech_exchange_state"]
        assert _sha256(data_dir / "attachments" / "fixture.txt") == expected["attachment_sha"]
        assert _sha256(data_dir / "config" / "authorization_issuer.pem") == expected["config_sha"]
        _assert_integrity(settings.db_path)

        first_hash = _sha256(settings.db_path)
        second = initialize_database_safely(settings)
        assert second.migrated is False and second.backup_path is None
        assert _sha256(settings.db_path) == first_hash
        assert not list(settings.backup_dir.glob("pre_upgrade_*.zip"))
        assert _schema_ledger(settings.db_path) == expected["schema_ledger"]
        assert _tech_exchange_state(settings.db_path) == expected["tech_exchange_state"]


def _assert_integrity(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_upgrade_fixture(source_version: str) -> None:
    close_db()
    with tempfile.TemporaryDirectory(prefix=f"jpt_{source_version}_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        expected = _seed_fixture(data_dir, source_version)
        settings = init_settings(Path(temp_dir) / "app")
        settings.data_dir = data_dir
        settings.db_path = data_dir / "database.sqlite"
        settings.upload_dir = data_dir / "attachments"
        settings.backup_dir = data_dir / "backups"
        settings.runtime_config_dir = data_dir / "config"
        settings.backup_dir.mkdir()

        result = initialize_database_safely(settings)
        assert result.migrated is True
        assert result.source_schema_version == expected["source_schema_version"]
        assert result.target_schema_version == APP_SCHEMA_VERSION
        assert result.backup_path and result.backup_path.is_file()
        assert result.backup_path.name.startswith(
            f"pre_upgrade_schema{expected['source_schema_version']}_to_schema"
            f"{APP_SCHEMA_VERSION}_"
        )
        assert read_app_schema_version(settings.db_path) == APP_SCHEMA_VERSION
        assert _counts(settings.db_path) == expected["counts"]
        assert _sha256(data_dir / "attachments" / "fixture.txt") == expected["attachment_sha"]
        assert _sha256(data_dir / "config" / "authorization_issuer.pem") == expected["config_sha"]
        assert _authorization_state(settings.db_path) == expected["authorization_state"]
        if expected["trip_planner_state"] is not None:
            _assert_migrated_trip_state(
                settings.db_path,
                expected["trip_planner_state"],
            )
        _assert_integrity(settings.db_path)
        conn = sqlite3.connect(str(settings.db_path))
        try:
            exchange_tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name LIKE 'tech_task_exchange_%'"
                ).fetchall()
            }
            assert exchange_tables == {
                "tech_task_exchange_batches", "tech_task_exchange_bindings"
            }
            if expected["tech_exchange_state"] is None:
                assert conn.execute(
                    "SELECT COUNT(*) FROM tech_task_exchange_batches"
                ).fetchone()[0] == 0
                assert conn.execute(
                    "SELECT COUNT(*) FROM tech_task_exchange_bindings"
                ).fetchone()[0] == 0
            else:
                assert _tech_exchange_state(settings.db_path) == expected["tech_exchange_state"]
            binding_columns = {
                row[1] for row in conn.execute(
                    "PRAGMA table_info(tech_task_exchange_bindings)"
                ).fetchall()
            }
            assert "last_exported_result_snapshot_json" in binding_columns
            ledger = conn.execute(
                "SELECT version, name, app_version FROM app_schema_migrations "
                "ORDER BY version"
            ).fetchall()
            assert [row[0] for row in ledger] == list(range(1, APP_SCHEMA_VERSION + 1))
            if source_version == "0.11.7-internal":
                assert ledger[0] == (1, "runtime_schema_v1", "0.11.7-internal")
        finally:
            conn.close()

        with zipfile.ZipFile(result.backup_path) as archive:
            names = archive.namelist()
            assert "attachments/fixture.txt" in names
            assert "config/authorization_issuer.pem" in names
            assert "config/desktop.lock" not in names
            assert "config/desktop_instance.json" not in names
            manifest = archive.read("manifest.json").decode("utf-8")
            assert '"backup_kind": "pre_upgrade"' in manifest
            assert f'"target_app_version": "{APP_VERSION}"' in manifest

        backup_count = len(list(settings.backup_dir.glob("pre_upgrade_*.zip")))
        first_hash = _sha256(settings.db_path)
        second = initialize_database_safely(settings)
        second_hash = _sha256(settings.db_path)
        assert second.migrated is False and second.backup_path is None
        assert first_hash == second_hash
        assert len(list(settings.backup_dir.glob("pre_upgrade_*.zip"))) == backup_count
        if expected["trip_planner_state"] is not None:
            _assert_migrated_trip_state(
                settings.db_path,
                expected["trip_planner_state"],
            )

        # A current ledger with missing required schema is treated as a repair
        # migration and still receives a pre-write backup.
        conn = sqlite3.connect(str(settings.db_path))
        try:
            conn.executescript(
                "DROP TABLE data_quality_issues; "
                "DROP TABLE import_bindings; DROP TABLE import_batches; "
                "ALTER TABLE trip_visit_briefings "
                "DROP COLUMN channel_partner_companions_json;"
            )
        finally:
            conn.close()
        repaired = initialize_database_safely(settings)
        assert repaired.migrated is True
        assert repaired.source_schema_version == APP_SCHEMA_VERSION
        assert repaired.backup_path
        assert repaired.backup_path.name.startswith(
            f"pre_upgrade_schema{APP_SCHEMA_VERSION}_to_schema{APP_SCHEMA_VERSION}_"
        )
        conn = sqlite3.connect(str(settings.db_path))
        try:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert {"import_batches", "import_bindings", "data_quality_issues"} <= names
        conn = sqlite3.connect(str(settings.db_path))
        try:
            briefing_columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(trip_visit_briefings)")
            }
        finally:
            conn.close()
        assert "channel_partner_companions_json" in briefing_columns
        assert _counts(settings.db_path) == expected["counts"]
        if expected["trip_planner_state"] is not None:
            close_db()
            service = AdminService(data_dir=data_dir)
            recovered = service.restore_database_from_backup(
                result.backup_path,
                preserve_current=True,
            )
            safety_db = Path(recovered["safety_database"])
            assert safety_db.is_file()
            _assert_integrity(safety_db)
            assert read_app_schema_version(settings.db_path) == V0118_SCHEMA_VERSION
            assert _counts(settings.db_path) == expected["counts"]
            assert _authorization_state(settings.db_path) == expected["authorization_state"]
            assert _tech_exchange_state(settings.db_path) == expected["tech_exchange_state"]
            assert _trip_planner_state(settings.db_path) == expected["trip_planner_state"]
            assert _sha256(data_dir / "attachments" / "fixture.txt") == expected["attachment_sha"]
            assert _sha256(data_dir / "config" / "authorization_issuer.pem") == expected["config_sha"]
            _assert_integrity(settings.db_path)


def test_a_migration_that_breaks_a_reference_is_refused() -> None:
    """Enforcement is off while the tables are rebuilt, so the commit checks it.

    A rebuild of a table other tables point at can only happen with reference
    enforcement turned off. That leaves one thing standing between a broken
    step and a saved database: the check before the commit.
    """
    close_db()
    with tempfile.TemporaryDirectory(prefix="jpt_orphan_upgrade_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        expected = _seed_fixture(data_dir, "0.11.4-internal")
        settings = init_settings(Path(temp_dir) / "app")
        settings.data_dir = data_dir
        settings.db_path = data_dir / "database.sqlite"
        settings.upload_dir = data_dir / "attachments"
        settings.backup_dir = data_dir / "backups"
        settings.runtime_config_dir = data_dir / "config"
        settings.backup_dir.mkdir()

        real_step = base._apply_runtime_schema_v13

        def leave_an_orphan(conn: sqlite3.Connection) -> None:
            real_step(conn)
            conn.execute(
                "INSERT INTO trip_plans (id,title,owner_id,status,created_at,"
                "updated_at,row_version) VALUES ('orphan-plan','Orphan',"
                "'user-that-never-existed','Draft',?,?,1)", (NOW, NOW))

        with patch.object(base, "_apply_runtime_schema_v13", leave_an_orphan):
            try:
                initialize_database_safely(settings)
            except RuntimeError as exc:
                assert "original database was restored" in str(exc), exc
            else:
                raise AssertionError(
                    "a migration that left a row pointing at nothing was committed"
                )

        assert _counts(settings.db_path) == expected["counts"]
        conn = sqlite3.connect(str(settings.db_path))
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM trip_plans WHERE id = 'orphan-plan'"
            ).fetchone()[0] == 0, "the broken row survived the restore"
        finally:
            conn.close()
        _assert_integrity(settings.db_path)
        print("PASS: a migration that breaks a reference is refused and restored")


def test_failed_migration_restores_original() -> None:
    close_db()
    with tempfile.TemporaryDirectory(prefix="jpt_failed_upgrade_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        expected = _seed_fixture(data_dir, "0.11.4-internal")
        settings = init_settings(Path(temp_dir) / "app")
        settings.data_dir = data_dir
        settings.db_path = data_dir / "database.sqlite"
        settings.upload_dir = data_dir / "attachments"
        settings.backup_dir = data_dir / "backups"
        settings.runtime_config_dir = data_dir / "config"
        settings.backup_dir.mkdir()

        def fail_after_write(db_path: Path, app_version: str) -> None:
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "INSERT INTO customers "
                    "(id, display_name, normalized_name, created_at, updated_at) "
                    "VALUES ('corrupt-write', 'Bad', 'bad', ?, ?)",
                    (NOW, NOW),
                )
                conn.commit()
            finally:
                conn.close()
            raise RuntimeError("simulated migration failure")

        with patch("backend.startup_upgrade.init_db", side_effect=fail_after_write):
            try:
                initialize_database_safely(settings)
            except RuntimeError as exc:
                assert "original database was restored" in str(exc)
            else:
                raise AssertionError("Expected simulated migration failure")

        assert _counts(settings.db_path) == expected["counts"]
        conn = sqlite3.connect(str(settings.db_path))
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM customers WHERE id = 'corrupt-write'"
            ).fetchone()[0] == 0
        finally:
            conn.close()
        assert _sha256(data_dir / "attachments" / "fixture.txt") == expected["attachment_sha"]
        assert _sha256(data_dir / "config" / "authorization_issuer.pem") == expected["config_sha"]
        _assert_integrity(settings.db_path)
        assert len(list(settings.backup_dir.glob("pre_upgrade_*.zip"))) == 1


def test_manual_recovery_is_scoped_and_preserves_current_database() -> None:
    close_db()
    with tempfile.TemporaryDirectory(prefix="jpt_manual_recovery_") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        _seed_fixture(data_dir, "0.11.4-internal")
        settings = init_settings(Path(temp_dir) / "app")
        settings.data_dir = data_dir
        settings.db_path = data_dir / "database.sqlite"
        settings.upload_dir = data_dir / "attachments"
        settings.backup_dir = data_dir / "backups"
        settings.runtime_config_dir = data_dir / "config"
        settings.backup_dir.mkdir()

        upgrade = initialize_database_safely(settings)
        assert upgrade.backup_path
        conn = sqlite3.connect(str(settings.db_path))
        try:
            conn.execute(
                "INSERT INTO customers "
                "(id, display_name, normalized_name, created_at, updated_at) "
                "VALUES ('manual-recovery-probe', 'Probe', 'probe', ?, ?)",
                (NOW, NOW),
            )
            conn.commit()
        finally:
            conn.close()

        service = AdminService(data_dir=data_dir)
        recovered = service.restore_database_from_backup(
            upgrade.backup_path,
            preserve_current=True,
        )
        safety_db = Path(recovered["safety_database"])
        assert safety_db.is_file()
        _assert_integrity(safety_db)
        conn = sqlite3.connect(str(safety_db))
        try:
            assert conn.execute(
                "SELECT COUNT(*) FROM customers WHERE id = 'manual-recovery-probe'"
            ).fetchone()[0] == 1
        finally:
            conn.close()
        assert read_app_schema_version(settings.db_path) == 0

        ordinary = Path(service.backup(settings.backup_dir, "test")["backup_path"])
        safety_count = len(list(settings.backup_dir.glob("pre_recovery_current_*.sqlite")))
        try:
            service.restore_database_from_backup(ordinary, preserve_current=True)
        except ValueError as exc:
            assert "pre-upgrade backup" in str(exc)
        else:
            raise AssertionError("ordinary full backup must not enter database-only recovery")
        assert len(list(settings.backup_dir.glob("pre_recovery_current_*.sqlite"))) == safety_count


def test_manual_recovery_aborts_when_safety_copy_fails() -> None:
    for failure_point in ("snapshot", "validation", "permissions"):
        close_db()
        with tempfile.TemporaryDirectory(
            prefix=f"jpt_recovery_safety_{failure_point}_",
        ) as temp_dir:
            data_dir = Path(temp_dir) / "data"
            _seed_fixture(data_dir, "0.11.4-internal")
            settings = init_settings(Path(temp_dir) / "app")
            settings.data_dir = data_dir
            settings.db_path = data_dir / "database.sqlite"
            settings.upload_dir = data_dir / "attachments"
            settings.backup_dir = data_dir / "backups"
            settings.runtime_config_dir = data_dir / "config"
            settings.backup_dir.mkdir()

            upgrade = initialize_database_safely(settings)
            assert upgrade.backup_path and upgrade.backup_path.is_file()
            conn = sqlite3.connect(str(settings.db_path))
            try:
                conn.execute(
                    "INSERT INTO customers "
                    "(id, display_name, normalized_name, created_at, updated_at) "
                    "VALUES ('safety-failure-probe', 'Probe', 'probe', ?, ?)",
                    (NOW, NOW),
                )
                conn.commit()
            finally:
                conn.close()

            sentinel = settings.backup_dir / "existing_backup.keep"
            sentinel.write_bytes(b"preserve-existing-backup")
            before_database = _sha256(settings.db_path)
            before_attachment = _sha256(data_dir / "attachments" / "fixture.txt")
            before_config = _sha256(data_dir / "config" / "authorization_issuer.pem")
            service = AdminService(data_dir=data_dir)
            original_snapshot = service._write_database_snapshot
            original_validate = service._validate_database_file
            path_type = type(settings.db_path)
            original_chmod = path_type.chmod

            def snapshot(path: Path) -> None:
                if "pre_recovery_current" in path.name:
                    raise PermissionError("simulated safety snapshot denial")
                original_snapshot(path)

            def validate(path: Path) -> None:
                if "pre_recovery_current" in path.name:
                    raise PermissionError("simulated safety validation denial")
                original_validate(path)

            def chmod(path: Path, mode: int) -> None:
                if "pre_recovery_current" in path.name:
                    raise PermissionError("simulated safety permission denial")
                original_chmod(path, mode)

            if failure_point == "snapshot":
                patch_target = patch.object(
                    service, "_write_database_snapshot", side_effect=snapshot,
                )
            elif failure_point == "validation":
                patch_target = patch.object(
                    service, "_validate_database_file", side_effect=validate,
                )
            else:
                patch_target = patch.object(path_type, "chmod", chmod)
            with patch_target:
                try:
                    service.restore_database_from_backup(
                        upgrade.backup_path,
                        preserve_current=True,
                    )
                except RuntimeError as exc:
                    assert "recovery was not started" in str(exc)
                else:
                    raise AssertionError(
                        f"Recovery continued after {failure_point} safety failure"
                    )

            assert _sha256(settings.db_path) == before_database
            assert _sha256(data_dir / "attachments" / "fixture.txt") == before_attachment
            assert _sha256(data_dir / "config" / "authorization_issuer.pem") == before_config
            assert sentinel.read_bytes() == b"preserve-existing-backup"
            assert upgrade.backup_path.is_file()
            assert not list(data_dir.glob(".database_failed_upgrade_*.sqlite"))
            assert not list(data_dir.glob(".database_upgrade_rollback_*.sqlite"))
            retained = list(settings.backup_dir.glob(
                ".pre_recovery_current_*.tmp.sqlite",
            ))
            if failure_point == "permissions":
                assert len(retained) == 1
                _assert_integrity(retained[0])
            else:
                assert not retained


def test_full_restore_aborts_when_pre_restore_backup_fails() -> None:
    close_db()
    with tempfile.TemporaryDirectory(prefix="jpt_pre_restore_safety_") as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "data"
        _seed_fixture(data_dir, "0.11.4-internal")
        service = AdminService(data_dir=data_dir)
        source_backup = Path(service.backup(
            root / "exports", "leader-1", apply_retention=False,
        )["backup_path"])

        conn = sqlite3.connect(str(data_dir / "database.sqlite"))
        try:
            conn.execute(
                "INSERT INTO customers "
                "(id, display_name, normalized_name, created_at, updated_at) "
                "VALUES ('pre-restore-probe', 'Probe', 'probe', ?, ?)",
                (NOW, NOW),
            )
            conn.commit()
        finally:
            conn.close()
        existing_backup = data_dir / "backups" / "existing.keep"
        existing_backup.parent.mkdir(parents=True, exist_ok=True)
        existing_backup.write_bytes(b"keep-existing")
        before_database = _sha256(data_dir / "database.sqlite")
        before_attachment = _sha256(data_dir / "attachments" / "fixture.txt")
        before_config = _sha256(data_dir / "config" / "authorization_issuer.pem")
        original_snapshot = service._write_database_snapshot

        def fail_pre_restore_snapshot(path: Path) -> None:
            if path.parent == existing_backup.parent and path.name.startswith(".backup_"):
                raise PermissionError("simulated pre-restore snapshot denial")
            original_snapshot(path)

        with patch.object(
            service,
            "_write_database_snapshot",
            side_effect=fail_pre_restore_snapshot,
        ):
            try:
                service.restore(source_backup, "leader-1")
            except RuntimeError as exc:
                assert "restore was not started" in str(exc)
            else:
                raise AssertionError("Restore continued without a validated safety backup")

        assert _sha256(data_dir / "database.sqlite") == before_database
        assert _sha256(data_dir / "attachments" / "fixture.txt") == before_attachment
        assert _sha256(data_dir / "config" / "authorization_issuer.pem") == before_config
        assert existing_backup.read_bytes() == b"keep-existing"
        assert source_backup.is_file()
        assert not list(data_dir.glob(".database_before_restore_*.sqlite"))
        assert not list(data_dir.glob(".attachments_before_restore_*"))
        assert not list(data_dir.glob(".config_before_restore_*"))


def main() -> None:
    for source_version in (
        "0.11.3-internal", "0.11.4-internal", "0.11.7-internal",
        "0.11.8-internal", "0.11.9-internal",
    ):
        test_upgrade_fixture(source_version)
        print(f"PASS: {source_version} upgrade fixture")
    for baseline in INTERMEDIATE_SCHEMA_BASELINES:
        test_intermediate_schema_upgrade(baseline)
    test_current_schema_fixture()
    print("PASS: current-schema no-migration fixture")
    test_a_migration_that_breaks_a_reference_is_refused()
    test_failed_migration_restores_original()
    print("PASS: failed migration restores validated original database")
    test_manual_recovery_is_scoped_and_preserves_current_database()
    print("PASS: manual recovery is scoped and preserves current database")
    test_manual_recovery_aborts_when_safety_copy_fails()
    print("PASS: manual recovery aborts before mutation when safety copy fails")
    test_full_restore_aborts_when_pre_restore_backup_fails()
    print("PASS: full restore aborts before mutation when safety backup fails")


if __name__ == "__main__":
    main()
