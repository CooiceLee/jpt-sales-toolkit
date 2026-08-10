#!/usr/bin/env python3
"""Run a frozen installer build against preserved legacy desktop data."""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.admin_service import AdminService
from backend.repositories import read_app_schema_version
from scripts.smoke_frozen import free_port, wait_for_health
from test_safe_upgrade import (
    _assert_integrity,
    _authorization_state,
    _counts,
    _seed_fixture,
    _sha256,
)


def _run_once(
    executable: Path,
    data_dir: Path,
    expect_disk_image: bool,
    launch_with_default_data_dir: bool,
) -> None:
    port = free_port()
    command = [str(executable), "--no-browser", "--port", str(port)]
    if not launch_with_default_data_dir:
        command.extend(["--data-dir", str(data_dir)])
    process = subprocess.Popen(command)
    try:
        wait_for_health(
            f"http://127.0.0.1:{port}",
            expect_disk_image=expect_disk_image,
            timeout=45,
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    if process.returncode not in (0, -15, 1):
        raise RuntimeError(f"Unexpected frozen upgrade process exit: {process.returncode}")


def _run_recovery(
    executable: Path,
    data_dir: Path,
    backup_path: Path,
    launch_with_default_data_dir: bool,
) -> None:
    env = os.environ.copy()
    env["JPT_SUPPRESS_RECOVERY_DIALOG"] = "1"
    command = [str(executable), "--no-browser"]
    if not launch_with_default_data_dir:
        command.extend(["--data-dir", str(data_dir)])
    command.extend(["--recover-backup", str(backup_path)])
    result = subprocess.run(
        command,
        check=False,
        timeout=45,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Packaged offline recovery failed: {result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument(
        "--fixture-version",
        choices=("0.11.3-internal", "0.11.4-internal", "0.11.7-internal"),
        required=True,
    )
    parser.add_argument("--expect-disk-image", action="store_true")
    parser.add_argument(
        "--launch-with-default-data-dir",
        action="store_true",
        help="Launch without --data-dir; the supplied fixture path must be the platform default.",
    )
    args = parser.parse_args()
    executable = args.executable.resolve()
    data_dir = args.data_dir.resolve()
    assert executable.is_file(), f"Frozen executable not found: {executable}"
    assert not data_dir.exists(), f"Upgrade fixture directory already exists: {data_dir}"
    if args.launch_with_default_data_dir:
        from desktop_runtime.paths import user_data_dir

        expected_default = user_data_dir().resolve()
        assert data_dir == expected_default, (
            f"Default data directory mismatch: fixture={data_dir}, runtime={expected_default}"
        )

    expected = _seed_fixture(data_dir, args.fixture_version)
    _run_once(
        executable,
        data_dir,
        args.expect_disk_image,
        args.launch_with_default_data_dir,
    )

    assert _counts(data_dir / "database.sqlite") == expected["counts"]
    assert _sha256(data_dir / "attachments" / "fixture.txt") == expected["attachment_sha"]
    assert _sha256(data_dir / "config" / "authorization_issuer.pem") == expected["config_sha"]
    assert _authorization_state(data_dir / "database.sqlite") == expected["authorization_state"]
    _assert_integrity(data_dir / "database.sqlite")
    backups = list((data_dir / "backups").glob("pre_upgrade_*.zip"))
    assert len(backups) == 1
    AdminService(data_dir=data_dir).validate_backup_archive(backups[0])

    # The second startup must not rewrite business data or create another
    # pre-upgrade backup after the schema ledger is current.
    first_hash = _sha256(data_dir / "database.sqlite")
    _run_once(
        executable,
        data_dir,
        args.expect_disk_image,
        args.launch_with_default_data_dir,
    )
    assert _sha256(data_dir / "database.sqlite") == first_hash
    assert len(list((data_dir / "backups").glob("pre_upgrade_*.zip"))) == 1

    # Recovery must be available from the installed executable itself. It
    # validates the archive, owns the normal instance lock and exits without
    # starting the web server.
    conn = sqlite3.connect(str(data_dir / "database.sqlite"))
    try:
        conn.execute(
            "INSERT INTO customers "
            "(id, display_name, normalized_name, created_at, updated_at) "
            "VALUES ('recovery-probe', 'Recovery Probe', 'recovery probe', "
            "'2026-07-01T00:00:00', '2026-07-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    _run_recovery(
        executable,
        data_dir,
        backups[0],
        args.launch_with_default_data_dir,
    )
    assert _counts(data_dir / "database.sqlite") == expected["counts"]
    assert read_app_schema_version(data_dir / "database.sqlite") == expected[
        "source_schema_version"
    ]
    assert _authorization_state(data_dir / "database.sqlite") == expected["authorization_state"]
    _assert_integrity(data_dir / "database.sqlite")
    safety_databases = list((data_dir / "backups").glob("pre_recovery_current_*.sqlite"))
    assert len(safety_databases) == 1
    _assert_integrity(safety_databases[0])
    conn = sqlite3.connect(str(safety_databases[0]))
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM customers WHERE id = 'recovery-probe'"
        ).fetchone()[0] == 1
    finally:
        conn.close()
    print(
        f"PASS: frozen {args.fixture_version} upgrade, preservation, idempotency and recovery"
    )


if __name__ == "__main__":
    main()
