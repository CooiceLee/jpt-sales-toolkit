#!/usr/bin/env python3
"""
Create isolated LAN demo accounts with one-time random passwords.

Usage:
    python3 scripts/create_test_accounts.py
    python3 scripts/create_test_accounts.py --data-dir data-test-server
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.config import init_settings  # noqa: E402
from backend.repositories import close_db, init_db  # noqa: E402
from backend.repositories.base import generate_uuid, get_db, now_iso  # noqa: E402


ACCOUNT_DEFINITIONS = [
    ("leader01", "Leader 01", "leader", None),
    ("sales01", "Sales 01", "sales", None),
    ("sales02", "Sales 02", "sales", None),
    ("sales03", "Sales 03", "sales", None),
    ("tech01", "Tech 01", "tech", None),
    ("tech02", "Tech 02", "tech", None),
]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def upsert_account(username: str, password: str, display_name: str, role: str, region: str | None) -> str:
    conn = get_db()
    now = now_iso()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    password_hash = hash_password(password)

    if existing:
        user_id = existing["id"]
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, display_name = ?, role = ?, region = ?, is_active = 1
            WHERE id = ?
            """,
            (password_hash, display_name, role, region, user_id),
        )
    else:
        user_id = generate_uuid()
        conn.execute(
            """
            INSERT INTO users (
                id, username, password_hash, display_name, role, region, is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (user_id, username, password_hash, display_name, role, region, now),
        )

    conn.commit()
    return user_id


def build_account_report(accounts: list[dict], data_dir: Path) -> str:
    lines = [
        "# JPT LAN Test Accounts",
        "",
        f"Data directory: `{data_dir}`",
        "",
        "| Source | Role | Username | Password | Display Name |",
        "|---|---|---|---|---|",
    ]
    for account in accounts:
        lines.append(
            f"| {account['source']} | {account['role']} | {account['username']} | {account['password']} | {account['display_name']} |"
        )
    lines.append("")
    lines.append("- `seed`：仅用于隔离测试库的演示账号；密码每次运行都会随机重签。")
    lines.append("- 本脚本不会修改测试库中其他既有成员的密码。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create LAN test accounts")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("JPT_DATA_DIR") or str(ROOT_DIR / "data-test-server"),
        help="Test data directory. Defaults to data-test-server.",
    )
    parser.add_argument(
        "--report-path",
        help="Optional markdown report output path for the refreshed account list.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    os.environ["JPT_DATA_DIR"] = str(data_dir)
    settings = init_settings(ROOT_DIR)
    init_db(settings.db_path)

    account_rows: list[dict] = []
    for username, display_name, role, region in ACCOUNT_DEFINITIONS:
        password = secrets.token_urlsafe(15)
        upsert_account(username, password, display_name, role, region)
        account_rows.append(
            {
                "source": "seed",
                "role": role,
                "username": username,
                "password": password,
                "display_name": display_name,
            }
        )

    report = build_account_report(account_rows, settings.data_dir)
    print(f"Data directory: {settings.data_dir}")

    if args.report_path:
        report_path = Path(args.report_path).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        report_path.chmod(0o600)
        print(f"Account report: {report_path}")
    else:
        print()
        print(report, end="")

    close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
