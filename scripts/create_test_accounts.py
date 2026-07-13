#!/usr/bin/env python3
"""
Create or refresh default LAN test accounts.

Usage:
    python3 scripts/create_test_accounts.py
    python3 scripts/create_test_accounts.py --data-dir data-test-server
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.config import init_settings  # noqa: E402
from backend.repositories import close_db, init_db  # noqa: E402
from backend.repositories.base import generate_uuid, get_db, now_iso  # noqa: E402


ACCOUNTS = [
    ("leader01", "LeaderJPT2026", "Leader 01", "leader", None),
    ("sales01", "Sales01JPT2026", "Sales 01", "sales", None),
    ("sales02", "Sales02JPT2026", "Sales 02", "sales", None),
    ("sales03", "Sales03JPT2026", "Sales 03", "sales", None),
    ("tech01", "Tech01JPT2026", "Tech 01", "tech", None),
    ("tech02", "Tech02JPT2026", "Tech 02", "tech", None),
]
PASSWORD_SUFFIX = "JPT2026"


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def normalize_password_token(value: str | None) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "", value or "")
    return token or "User"


def lan_password_for_existing_user(username: str, display_name: str | None) -> str:
    base = normalize_password_token(display_name) or normalize_password_token(username)
    return f"{base}{PASSWORD_SUFFIX}"


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


def refresh_existing_users() -> list[dict]:
    conn = get_db()
    seeded_usernames = {username for username, *_ in ACCOUNTS}
    rows = conn.execute(
        """
        SELECT id, username, display_name, role, region
        FROM users
        WHERE is_active = 1
        ORDER BY
            CASE role
                WHEN 'leader' THEN 0
                WHEN 'sales' THEN 1
                WHEN 'tech' THEN 2
                ELSE 9
            END,
            username
        """
    ).fetchall()

    refreshed: list[dict] = []
    for row in rows:
        username = row["username"]
        if username in seeded_usernames:
            continue
        password = lan_password_for_existing_user(username, row["display_name"])
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, is_active = 1
            WHERE id = ?
            """,
            (hash_password(password), row["id"]),
        )
        refreshed.append(
            {
                "source": "existing",
                "role": row["role"],
                "username": username,
                "password": password,
                "display_name": row["display_name"] or username,
            }
        )

    conn.commit()
    return refreshed


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
    lines.append("- `seed`：脚本固定创建的演示账号。")
    lines.append("- `existing`：当前测试库已有团队账号，已刷新为可登录的 LAN 测试密码。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create LAN test accounts")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("JPT_DATA_DIR") or str(ROOT_DIR / "data-test-server"),
        help="Test data directory. Defaults to data-test-server.",
    )
    parser.add_argument(
        "--include-existing-users",
        action="store_true",
        help="Also refresh existing active users in the database with deterministic LAN test passwords.",
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
    for username, password, display_name, role, region in ACCOUNTS:
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

    if args.include_existing_users:
        account_rows.extend(refresh_existing_users())

    report = build_account_report(account_rows, settings.data_dir)
    print(f"Data directory: {settings.data_dir}")
    print()
    print(report, end="")

    if args.report_path:
        report_path = Path(args.report_path).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        print(f"Account report: {report_path}")

    close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
