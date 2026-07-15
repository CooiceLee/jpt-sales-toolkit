"""Regression tests for secret-bearing runtime config backup and restore."""

from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from backend.services.admin_service import AdminService


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
        assert (data_dir / "config" / "jwt_secret").read_text() == "jwt-current"
        assert (data_dir / "config" / "authorization_issuer.pem").read_text() == "issuer-current"


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
            if path.name == "config" and path.parent.name.startswith(".restore_stage_"):
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


def main() -> None:
    test_runtime_config_round_trip()
    test_legacy_backup_preserves_runtime_config()
    test_config_install_failure_rolls_back_all_data()
    print("PASS: runtime config backup, compatibility, and rollback")


if __name__ == "__main__":
    main()
