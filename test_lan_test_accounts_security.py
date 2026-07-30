#!/usr/bin/env python3
"""LAN demo account seeding must not weaken existing team credentials."""

from __future__ import annotations

import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.repositories.base import init_db


ROOT = Path(__file__).parent


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt-lan-accounts-") as directory:
        data_dir = Path(directory)
        database = data_dir / "database.sqlite"
        report = data_dir / "lan_test_accounts.md"
        init_db(database)
        conn = sqlite3.connect(database)
        conn.execute(
            """
            INSERT INTO users
                (id, username, password_hash, display_name, role, is_active, created_at)
            VALUES
                ('real-member', 'real.member', 'must-stay-unchanged',
                 'Real Member', 'sales', 1, '2026-07-30T00:00:00')
            """
        )
        conn.commit()
        conn.close()

        result = subprocess.run(
            [
                sys.executable,
                "scripts/create_test_accounts.py",
                "--data-dir",
                str(data_dir),
                "--report-path",
                str(report),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr or result.stdout

        conn = sqlite3.connect(database)
        existing_hash = conn.execute(
            "SELECT password_hash FROM users WHERE id = 'real-member'"
        ).fetchone()[0]
        demo_count = conn.execute(
            "SELECT COUNT(*) FROM users WHERE username LIKE 'leader%' "
            "OR username LIKE 'sales0%' OR username LIKE 'tech0%'"
        ).fetchone()[0]
        conn.close()

        assert existing_hash == "must-stay-unchanged"
        assert demo_count == 6
        assert stat.S_IMODE(report.stat().st_mode) == 0o600
        text = report.read_text(encoding="utf-8")
        assert "real.member" not in text
        assert "JPT2026" not in text

    print("PASS: LAN demo credentials are random, private and isolated")


if __name__ == "__main__":
    main()
