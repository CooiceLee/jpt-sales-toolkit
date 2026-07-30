"""Regression tests for secret-bearing runtime config backup and restore."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.services.admin_service import AdminService
from desktop_runtime.instance import InstanceLock


def write_database(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS state (value TEXT NOT NULL)")
        connection.execute("DELETE FROM state")
        connection.execute("INSERT INTO state (value) VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def read_database(path: Path) -> str:
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute("SELECT value FROM state").fetchone()[0]
    finally:
        connection.close()


def seed_data(data_dir: Path, value: str) -> None:
    write_database(data_dir / "database.sqlite", value)
    attachments = data_dir / "attachments"
    attachments.mkdir(parents=True, exist_ok=True)
    (attachments / "evidence.txt").write_text(value, encoding="utf-8")
    runtime_config = data_dir / "config"
    runtime_config.mkdir(parents=True, exist_ok=True)
    (runtime_config / "jwt_secret").write_text(f"jwt-{value}", encoding="utf-8")
    (runtime_config / "authorization_issuer.pem").write_text(
        f"issuer-{value}", encoding="utf-8"
    )


def clone_archive_with_members(
    source: Path,
    target: Path,
    members: list[tuple[object, bytes]],
) -> None:
    """Copy a valid backup and append deliberately hostile ZIP members."""
    with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(
        target, "w", zipfile.ZIP_DEFLATED,
    ) as altered:
        for info in original.infolist():
            altered.writestr(info, original.read(info))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            for name, payload in members:
                altered.writestr(name, payload)


def test_runtime_config_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        backup_dir = root / "exports"
        seed_data(data_dir, "backup")

        service = AdminService(data_dir=data_dir)
        result = service.backup(backup_dir, "leader-1")
        backup_path = Path(result["backup_path"])

        with zipfile.ZipFile(backup_path) as archive:
            names = archive.namelist()
            assert "config/" in names
            assert "config/jwt_secret" in names
            assert "config/authorization_issuer.pem" in names
        assert "config/" in result["manifest"]["contents"]

        seed_data(data_dir, "current")
        (data_dir / "config" / "current_only").write_text("remove", encoding="utf-8")
        service.restore(backup_path, "leader-1")

        assert read_database(data_dir / "database.sqlite") == "backup"
        assert (data_dir / "attachments" / "evidence.txt").read_text() == "backup"
        assert (data_dir / "config" / "jwt_secret").read_text() == "jwt-backup"
        assert (data_dir / "config" / "authorization_issuer.pem").read_text() == "issuer-backup"
        assert not (data_dir / "config" / "current_only").exists()
        if os.name == "posix":
            mode = stat.S_IMODE((data_dir / "config" / "jwt_secret").stat().st_mode)
            assert mode == 0o600, oct(mode)


def test_legacy_backup_preserves_runtime_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        seed_data(data_dir, "current")
        legacy_db = root / "legacy.sqlite"
        write_database(legacy_db, "legacy")
        legacy_backup = root / "legacy.zip"
        with zipfile.ZipFile(legacy_backup, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(legacy_db, "database.sqlite")
            archive.writestr("manifest.json", '{"contents":["database.sqlite"]}')

        AdminService(data_dir=data_dir).restore(legacy_backup, "leader-1")

        assert read_database(data_dir / "database.sqlite") == "legacy"
        assert (data_dir / "attachments" / "evidence.txt").read_text() == "current"
        assert (data_dir / "config" / "jwt_secret").read_text() == "jwt-current"
        assert (data_dir / "config" / "authorization_issuer.pem").read_text() == "issuer-current"


def write_legacy_full_backup(root: Path, backup_path: Path) -> None:
    legacy_db = root / "legacy-full.sqlite"
    write_database(legacy_db, "legacy-full")
    payloads = {
        "attachments/evidence.txt": b"legacy-attachment",
        "config/authorization_clock.json": b'{"clock":"legacy"}',
        "config/authorization_issuer.pem": b"legacy-issuer",
        "config/jwt_secret": b"legacy-jwt",
        "config/desktop.lock": b"archived-lock",
        "config/desktop_instance.json": b'{"port":9999}',
        "config/desktop_instance.tmp": b'{"port":9998}',
    }
    contents = [
        "database.sqlite",
        "attachments/",
        "config/",
        *payloads,
    ]
    manifest = {
        "backup_time": "2026-07-17T04:18:56",
        "backup_by": "legacy-leader",
        "version": "0.11.3-internal",
        "contents": contents,
    }
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(legacy_db, "database.sqlite")
        archive.writestr("attachments/", b"")
        archive.writestr("config/", b"")
        for name, payload in payloads.items():
            archive.writestr(name, payload)
        archive.writestr("manifest.json", json.dumps(manifest))


def test_legacy_full_backup_restores_safe_data_and_preserves_live_lock() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        seed_data(data_dir, "current")
        config_dir = data_dir / "config"
        (config_dir / "authorization_clock.json").write_text(
            '{"clock":"current"}', encoding="utf-8"
        )
        (config_dir / "current_only").write_text("remove", encoding="utf-8")
        (config_dir / "desktop_instance.json").write_text(
            '{"port":8765}', encoding="utf-8"
        )
        (config_dir / "desktop_instance.tmp").write_text(
            '{"port":8766}', encoding="utf-8"
        )

        backup_path = root / "legacy-full.zip"
        write_legacy_full_backup(root, backup_path)
        primary_lock = InstanceLock(config_dir / "desktop.lock")
        assert primary_lock.acquire()
        try:
            result = AdminService(data_dir=data_dir).restore(
                backup_path,
                "leader-1",
                create_pre_restore=False,
            )
            competing_lock = InstanceLock(config_dir / "desktop.lock")
            assert not competing_lock.acquire(), "restore must preserve the live lock inode"
        finally:
            primary_lock.release()

        assert read_database(data_dir / "database.sqlite") == "legacy-full"
        assert (data_dir / "attachments" / "evidence.txt").read_text() == "legacy-attachment"
        assert (config_dir / "jwt_secret").read_text() == "legacy-jwt"
        assert (config_dir / "authorization_issuer.pem").read_text() == "legacy-issuer"
        assert (config_dir / "authorization_clock.json").read_text() == '{"clock":"legacy"}'
        assert (config_dir / "desktop_instance.json").read_text() == '{"port":8765}'
        assert (config_dir / "desktop_instance.tmp").read_text() == '{"port":8766}'
        assert not (config_dir / "current_only").exists()
        inventory = result["manifest"]["files"]
        assert "config/jwt_secret" in inventory
        assert "config/desktop.lock" not in inventory
        assert "config/desktop_instance.json" not in inventory
        assert result["manifest"]["_legacy_inventory_synthesized"] is True


def test_legacy_full_backup_requires_exact_contents_before_writes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        seed_data(data_dir, "current")
        legacy_db = root / "legacy.sqlite"
        write_database(legacy_db, "legacy")
        hostile = root / "legacy-unlisted.zip"
        with zipfile.ZipFile(hostile, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(legacy_db, "database.sqlite")
            archive.writestr("config/injected", b"malicious")
            archive.writestr(
                "manifest.json",
                json.dumps({"contents": ["database.sqlite"]}),
            )

        try:
            AdminService(data_dir=data_dir).restore(hostile, "leader-1")
        except ValueError as exc:
            assert "unlisted legacy member" in str(exc)
        else:
            raise AssertionError("Legacy archive with an unlisted member was accepted")

        assert read_database(data_dir / "database.sqlite") == "current"
        assert not list((data_dir / "backups").glob("backup_*.zip"))


def test_config_install_failure_rolls_back_all_data() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        backup_dir = root / "exports"
        seed_data(data_dir, "backup")
        service = AdminService(data_dir=data_dir)
        backup_path = Path(service.backup(backup_dir, "leader-1")["backup_path"])
        seed_data(data_dir, "current")

        path_type = type(data_dir)
        original_replace = path_type.replace

        def fail_staged_config(path: Path, target: Path) -> Path:
            if (
                path.name == "jwt_secret"
                and path.parent.name == "config"
                and path.parent.parent.name.startswith(".restore_stage_")
            ):
                raise OSError("simulated config install failure")
            return original_replace(path, target)

        try:
            with patch.object(path_type, "replace", fail_staged_config):
                service.restore(backup_path, "leader-1")
        except OSError as exc:
            assert "simulated config install failure" in str(exc)
        else:
            raise AssertionError("Expected simulated restore failure")

        assert read_database(data_dir / "database.sqlite") == "current"
        assert (data_dir / "attachments" / "evidence.txt").read_text() == "current"
        assert (data_dir / "config" / "jwt_secret").read_text() == "jwt-current"
        assert (data_dir / "config" / "authorization_issuer.pem").read_text() == "issuer-current"


def test_restore_rejects_unlisted_and_unsafe_archive_members() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        exports = root / "exports"
        seed_data(data_dir, "backup")
        service = AdminService(data_dir=data_dir)
        valid_backup = Path(service.backup(
            exports, "leader-1", apply_retention=False,
        )["backup_path"])
        seed_data(data_dir, "current")

        symlink = zipfile.ZipInfo("attachments/link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        special_file = zipfile.ZipInfo("attachments/pipe")
        special_file.create_system = 3
        special_file.external_attr = (stat.S_IFIFO | 0o600) << 16
        cases = (
            ("unlisted-config.zip", [("config/injected_secret", b"malicious")]),
            ("unlisted-attachment.zip", [("attachments/injected.txt", b"malicious")]),
            ("traversal.zip", [("attachments/../../escaped.txt", b"malicious")]),
            ("absolute.zip", [("/config/absolute", b"malicious")]),
            ("backslash.zip", [("config\\windows-path", b"malicious")]),
            ("trailing-dot.zip", [("attachments/report.", b"malicious")]),
            ("trailing-space.zip", [("attachments/report ", b"malicious")]),
            ("duplicate.zip", [("config/jwt_secret", b"duplicate")]),
            (
                "normalized-duplicate.zip",
                [
                    ("attachments/caf\u00e9.txt", b"one"),
                    ("attachments/cafe\u0301.txt", b"two"),
                ],
            ),
            ("symlink.zip", [(symlink, b"target")]),
            ("special-file.zip", [(special_file, b"pipe")]),
        )
        for filename, members in cases:
            hostile = root / filename
            clone_archive_with_members(valid_backup, hostile, members)
            try:
                service.restore(hostile, "leader-1")
            except ValueError as exc:
                assert any(
                    label in str(exc).lower()
                    for label in (
                        "unlisted", "unsafe", "duplicate", "symbolic", "special",
                    )
                ), str(exc)
            else:
                raise AssertionError(f"Hostile archive was accepted: {filename}")

            assert read_database(data_dir / "database.sqlite") == "current"
            assert (data_dir / "attachments" / "evidence.txt").read_text() == "current"
            assert (data_dir / "config" / "jwt_secret").read_text() == "jwt-current"
            assert not (data_dir / "config" / "injected_secret").exists()
            assert not (data_dir / "attachments" / "injected.txt").exists()
            assert not (root / "escaped.txt").exists()


def test_restore_rejects_uncompressed_size_over_limit() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data_dir = root / "data"
        seed_data(data_dir, "backup")
        service = AdminService(data_dir=data_dir)
        backup_path = Path(service.backup(
            root / "exports", "leader-1", apply_retention=False,
        )["backup_path"])
        seed_data(data_dir, "current")

        with patch.object(AdminService, "_MAX_BACKUP_EXTRACTED_SIZE", 128):
            try:
                service.restore(backup_path, "leader-1")
            except ValueError as exc:
                assert "size limit" in str(exc).lower()
            else:
                raise AssertionError("Oversized extracted archive was accepted")

        with patch.object(AdminService, "_COMPRESSION_RATIO_MIN_SIZE", 1), patch.object(
            AdminService, "_MAX_BACKUP_COMPRESSION_RATIO", 1,
        ):
            try:
                service.validate_backup_archive(backup_path)
            except ValueError as exc:
                assert "compression ratio" in str(exc).lower()
            else:
                raise AssertionError("Excessive compression ratio was accepted")

        assert read_database(data_dir / "database.sqlite") == "current"
        assert (data_dir / "attachments" / "evidence.txt").read_text() == "current"
        assert (data_dir / "config" / "jwt_secret").read_text() == "jwt-current"


def main() -> None:
    test_runtime_config_round_trip()
    test_legacy_backup_preserves_runtime_config()
    test_legacy_full_backup_restores_safe_data_and_preserves_live_lock()
    test_legacy_full_backup_requires_exact_contents_before_writes()
    test_config_install_failure_rolls_back_all_data()
    test_restore_rejects_unlisted_and_unsafe_archive_members()
    test_restore_rejects_uncompressed_size_over_limit()
    print(
        "PASS: runtime config backup, compatibility, rollback, and hostile ZIP rejection"
    )


if __name__ == "__main__":
    main()
