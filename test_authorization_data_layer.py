"""Focused regression tests for authorization schema migration and repositories."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from backend.repositories import (
    AuthorizationEventRepository,
    DeviceAuthorizationRepository,
    OrganizationRepository,
    UserCredentialRepository,
    UserRepository,
    close_db,
    init_db,
)


AUTH_TABLES = {
    "schema_migrations",
    "organizations",
    "user_credentials",
    "device_authorizations",
    "authorization_events",
}
DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def _expect_value_error(action, expected_text: str) -> None:
    try:
        action()
    except ValueError as exc:
        assert expected_text in str(exc)
        return
    raise AssertionError("Expected ValueError")


def _create_legacy_database(db_path: Path) -> list[tuple]:
    """Build a pre-authorization database shaped like an existing local install."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            region TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        );
        CREATE TABLE customers (id TEXT PRIMARY KEY);
        CREATE TABLE customer_contacts (id TEXT PRIMARY KEY);
        CREATE TABLE leads (
            id TEXT PRIMARY KEY,
            owner_id TEXT,
            sales_stage TEXT,
            service_status TEXT,
            archived_at TEXT,
            updated_at TEXT,
            row_version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE lead_assignments (
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            user_id TEXT,
            assignment_type TEXT,
            created_at TEXT,
            archived_at TEXT
        );
        CREATE TABLE lead_activities (
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            action_type TEXT
        );
        CREATE TABLE after_sales_tasks (
            id TEXT PRIMARY KEY,
            lead_id TEXT,
            status TEXT,
            archived_at TEXT
        );
        CREATE TABLE legacy_business_data (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        );
        """
    )
    users = [
        (
            "legacy-leader",
            "leader.old",
            "legacy-hash-1",
            "Legacy Leader",
            "leader",
            "EU",
            1,
            "2025-01-01T00:00:00",
            None,
        ),
        (
            "legacy-tech",
            "tech.old",
            "legacy-hash-2",
            "Legacy Tech",
            "tech",
            None,
            0,
            "2025-02-01T00:00:00",
            None,
        ),
    ]
    conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", users)
    conn.execute(
        "INSERT INTO legacy_business_data VALUES (?, ?)",
        ("business-1", '{"must":"remain byte-identical"}'),
    )
    conn.commit()
    conn.close()
    return users


def _add_v1_authorization_row(db_path: Path) -> None:
    """Simulate a database that already applied authorization schema v1."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        f"""
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE organizations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            authorization_provider TEXT NOT NULL DEFAULT 'offline',
            authorization_duration_days INTEGER NOT NULL DEFAULT 90,
            signing_key_id TEXT,
            signing_public_key TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deactivated_at TEXT
        );
        CREATE TABLE device_authorizations (
            id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL REFERENCES organizations(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            device_fingerprint_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            authorization_version INTEGER NOT NULL DEFAULT 1,
            payload_json TEXT NOT NULL,
            signature TEXT NOT NULL,
            signature_algorithm TEXT NOT NULL DEFAULT 'ed25519',
            signing_key_id TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT REFERENCES users(id),
            updated_at TEXT NOT NULL,
            deactivated_at TEXT,
            deactivation_reason TEXT,
            replaced_by_id TEXT REFERENCES device_authorizations(id)
        );
        INSERT INTO schema_migrations VALUES (
            1, 'authorization_data_layer_v1', '2025-01-01T00:00:00'
        );
        INSERT INTO organizations (
            id, name, slug, authorization_provider,
            authorization_duration_days, is_active, created_at, updated_at
        ) VALUES (
            '{DEFAULT_ORGANIZATION_ID}', 'Existing Team', 'existing-team',
            'offline', 90, 1, '2025-01-01T00:00:00', '2025-01-01T00:00:00'
        );
        INSERT INTO device_authorizations (
            id, organization_id, user_id, device_fingerprint_hash, role,
            payload_json, signature, signing_key_id, issued_at, valid_from,
            expires_at, created_by, updated_at
        ) VALUES (
            'v1-package', '{DEFAULT_ORGANIZATION_ID}', 'legacy-leader',
            '{'d' * 64}', 'leader', '{{"version":1}}', 'v1-signature',
            'v1-key', '2025-01-01T00:00:00', '2025-01-01T00:00:00',
            '2030-01-01T00:00:00', 'legacy-leader', '2025-01-01T00:00:00'
        );
        INSERT INTO device_authorizations (
            id, organization_id, user_id, device_fingerprint_hash, role,
            payload_json, signature, signing_key_id, issued_at, valid_from,
            expires_at, created_by, updated_at
        ) VALUES (
            'v1-duplicate-device', '{DEFAULT_ORGANIZATION_ID}', 'legacy-tech',
            '{'d' * 64}', 'tech', '{{"version":1}}', 'old-signature',
            'v1-key', '2024-01-01T00:00:00', '2024-01-01T00:00:00',
            '2030-01-01T00:00:00', 'legacy-leader', '2024-01-01T00:00:00'
        );
        """
    )
    conn.commit()
    conn.close()


def test_existing_database_migration_preserves_data() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "legacy.sqlite"
        expected_users = _create_legacy_database(db_path)
        close_db()
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        migrated_users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        expected_sorted = sorted(expected_users, key=lambda row: row[0])
        assert migrated_users == expected_sorted
        assert conn.execute("SELECT payload FROM legacy_business_data").fetchone()[0] == (
            '{"must":"remain byte-identical"}'
        )
        credentials = conn.execute(
            """
            SELECT user_id, password_hash, password_scheme, must_change_password, is_active
            FROM user_credentials ORDER BY user_id
            """
        ).fetchall()
        assert credentials == [
            ("legacy-leader", "legacy-hash-1", "legacy_sha256", 1, 1),
            ("legacy-tech", "legacy-hash-2", "legacy_sha256", 1, 0),
        ]
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
        conn.close()

        credential_repo = UserCredentialRepository()
        leader_credential = credential_repo.get_by_user_id("legacy-leader")
        assert leader_credential is not None
        credential_repo.update(
            leader_credential["id"],
            {
                "password_hash": "new-self-contained-hash",
                "password_scheme": "pbkdf2_sha256",
                "must_change_password": False,
            },
        )
        close_db()
        init_db(db_path)
        migrated = UserCredentialRepository().get_by_user_id("legacy-leader")
        assert migrated is not None
        assert migrated["password_hash"] == "new-self-contained-hash"
        assert migrated["password_scheme"] == "pbkdf2_sha256"
        assert UserCredentialRepository().count() == 2
        close_db()


def test_v1_authorization_migrates_to_issued_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "authorization-v1.sqlite"
        _create_legacy_database(db_path)
        _add_v1_authorization_row(db_path)
        close_db()
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(device_authorizations)")
        }
        assert "activation_state" in columns
        assert conn.execute(
            "SELECT activation_state FROM device_authorizations WHERE id = 'v1-package'"
        ).fetchone() == ("issued",)
        assert conn.execute(
            """
            SELECT activation_state, is_active, deactivation_reason, replaced_by_id
            FROM device_authorizations WHERE id = 'v1-duplicate-device'
            """
        ).fetchone() == (
            "issued",
            0,
            "migration_device_conflict",
            "v1-package",
        )
        assert conn.execute(
            "SELECT name FROM schema_migrations WHERE version = 2"
        ).fetchone() == ("authorization_data_layer_v2",)
        conn.close()

        authorizations = DeviceAuthorizationRepository()
        assert authorizations.get_active_for_user("legacy-leader")["id"] == "v1-package"
        assert authorizations.get_active_for_device("d" * 64) is None
        assert authorizations.update("v1-package", {"activation_state": "activated"})
        assert authorizations.get_active_for_device("d" * 64)["id"] == "v1-package"
        close_db()


def test_fresh_schema_and_repository_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "fresh.sqlite"
        close_db()
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert AUTH_TABLES <= tables
        assert conn.execute("SELECT name FROM schema_migrations WHERE version = 2").fetchone() == (
            "authorization_data_layer_v2",
        )
        conn.close()

        organizations = OrganizationRepository()
        default_org = organizations.get_default()
        assert default_org is not None
        assert default_org["authorization_duration_days"] == 90
        remote_org_id = organizations.create(
            {
                "name": "Future Remote Team",
                "slug": "future-remote",
                "authorization_provider": "remote",
                "authorization_duration_days": 30,
            }
        )
        assert organizations.get_by_slug("future-remote")["id"] == remote_org_id
        assert organizations.update(remote_org_id, {"authorization_duration_days": 45})
        assert organizations.deactivate(remote_org_id)
        assert organizations.get_by_id(remote_org_id)["is_active"] == 0
        assert organizations.reactivate(remote_org_id)
        assert organizations.get_by_id(remote_org_id)["is_active"] == 1

        user_id = UserRepository().create(
            username="sales.auth",
            password_hash="legacy-profile-hash",
            display_name="Authorization Sales",
            role="sales",
            region="EU",
        )
        credentials = UserCredentialRepository()
        credential_id = credentials.create(
            {
                "user_id": user_id,
                "password_hash": "pbkdf2-hash-1",
                "password_scheme": "pbkdf2_sha256",
                "must_change_password": True,
            }
        )
        assert credentials.get_by_user_id(user_id, active_only=True)["id"] == credential_id
        assert "password_hash" not in credentials.list_by_organization()[0]
        assert credentials.update(
            credential_id,
            {"password_hash": "pbkdf2-hash-2", "must_change_password": False},
        )
        assert credentials.get_by_id(credential_id)["password_changed_at"] is not None
        assert credentials.deactivate(credential_id)
        assert credentials.get_by_user_id(user_id, active_only=True) is None
        assert credentials.reactivate(credential_id)

        authorizations = DeviceAuthorizationRepository()
        first_data = {
            "user_id": user_id,
            "device_fingerprint_hash": "a" * 64,
            "role": "sales",
            "payload_json": {"user_id": user_id, "role": "sales"},
            "signature": "signature-1",
            "signing_key_id": "leader-key-1",
            "created_by": user_id,
        }
        first_id = authorizations.create(first_data)
        first = authorizations.get_active_for_user(user_id)
        assert first is not None and first["id"] == first_id
        assert first["activation_state"] == "issued"
        assert authorizations.get_active_for_device("a" * 64) is None
        assert json.loads(first["payload_json"])["role"] == "sales"
        validity = datetime.fromisoformat(first["expires_at"]) - datetime.fromisoformat(
            first["valid_from"]
        )
        assert validity.days == 90
        assert authorizations.update(first_id, {"signature": "signature-1-updated"})
        assert authorizations.update(first_id, {"activation_state": "activated"})
        assert authorizations.get_active_for_device("a" * 64)["id"] == first_id
        _expect_value_error(
            lambda: authorizations.update(first_id, {"activation_state": "invalid"}),
            "Unsupported activation state",
        )

        other_user_id = UserRepository().create(
            username="sales.same-device",
            password_hash="other-profile-hash",
            display_name="Same Device Sales",
            role="sales",
        )
        _expect_value_error(
            lambda: authorizations.create(
                {
                    **first_data,
                    "user_id": other_user_id,
                    "created_by": other_user_id,
                }
            ),
            "Device already has an active authorization",
        )

        duplicate = {
            **first_data,
            "device_fingerprint_hash": "b" * 64,
            "activation_state": "activated",
        }
        _expect_value_error(
            lambda: authorizations.create(duplicate),
            "already has an active device authorization",
        )
        assert authorizations.deactivate(first_id, "manual_test")
        assert authorizations.reactivate(first_id)

        replacement_id = authorizations.replace_active(
            {**duplicate, "signature": "signature-2"}
        )
        assert authorizations.get_active_for_user(user_id)["id"] == replacement_id
        assert authorizations.get_active_for_device("b" * 64)["id"] == replacement_id
        first_history = authorizations.get_by_id(first_id)
        assert first_history["is_active"] == 0
        assert first_history["replaced_by_id"] == replacement_id
        _expect_value_error(
            lambda: authorizations.reactivate(first_id),
            "already has an active device authorization",
        )
        failed_replacement = {
            **duplicate,
            "device_fingerprint_hash": "c" * 64,
            "created_by": "missing-actor",
        }
        try:
            authorizations.replace_active(failed_replacement)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Invalid replacement should violate its foreign key")
        assert authorizations.get_active_for_user(user_id)["id"] == replacement_id
        assert len(authorizations.list_for_user(user_id)) == 2

        events = AuthorizationEventRepository()
        event_id = events.create(
            {
                "user_id": user_id,
                "device_authorization_id": replacement_id,
                "actor_user_id": user_id,
                "event_type": "authorization_reissued",
                "event_data_json": {"reason": "device_changed"},
            }
        )
        assert events.get_by_id(event_id)["event_type"] == "authorization_reissued"
        assert events.list_for_user(user_id)[0]["id"] == event_id
        assert events.list_for_authorization(replacement_id)[0]["id"] == event_id
        assert events.list_recent(DEFAULT_ORGANIZATION_ID)[0]["id"] == event_id
        try:
            events.delete_by_id(event_id)
        except NotImplementedError as exc:
            assert "append-only" in str(exc)
        else:
            raise AssertionError("Authorization events must be append-only")
        close_db()


def main() -> None:
    tests = [
        test_existing_database_migration_preserves_data,
        test_v1_authorization_migrates_to_issued_state,
        test_fresh_schema_and_repository_lifecycle,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print("PASS: authorization data layer validation completed")


if __name__ == "__main__":
    main()
