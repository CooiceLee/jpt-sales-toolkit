#!/usr/bin/env python3
"""
Create a full backup for the LAN test-server data directory.

Usage:
    python3 scripts/backup_test_server.py
    python3 scripts/backup_test_server.py --data-dir data-test-server
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.config import init_settings  # noqa: E402
from backend.repositories import close_db, init_db  # noqa: E402
from backend.services.admin_service import AdminService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up LAN test-server data")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("JPT_DATA_DIR") or str(ROOT_DIR / "data-test-server"),
        help="Test data directory. Defaults to data-test-server.",
    )
    parser.add_argument(
        "--actor",
        default="manual-test-server-backup",
        help="Actor id written into backup manifest.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    os.environ["JPT_DATA_DIR"] = str(data_dir)
    settings = init_settings(ROOT_DIR)
    init_db(settings.db_path)

    service = AdminService(data_dir=settings.data_dir)
    result = service.backup(settings.backup_dir, args.actor)
    print(result["backup_path"])
    print(f"size={result['backup_size']}")
    print(f"cleanup_deleted={result.get('cleanup', {}).get('deleted', 0)}")

    close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
