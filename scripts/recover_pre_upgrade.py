#!/usr/bin/env python3
"""Offline recovery from a validated automatic pre-upgrade archive."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.admin_service import AdminService
from desktop_runtime.instance import InstanceLock
from desktop_runtime.paths import user_data_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore SQLite from a JPT pre-upgrade backup while JPT is stopped"
    )
    parser.add_argument("backup", type=Path)
    parser.add_argument("--data-dir", help="Override the platform JPT data directory")
    args = parser.parse_args()

    data_dir = user_data_dir(args.data_dir)
    lock_path = data_dir / "config" / "desktop.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = InstanceLock(lock_path)
    if not lock.acquire():
        raise SystemExit("JPT is still running. Exit JPT completely before recovery.")
    try:
        result = AdminService(data_dir=data_dir).restore_database_from_backup(
            args.backup.expanduser().resolve(),
            preserve_current=True,
        )
    finally:
        lock.release()
    print(f"PASS: restored database from {result['source_backup']}")
    print(f"Safety database: {result['safety_database']}")


if __name__ == "__main__":
    main()
