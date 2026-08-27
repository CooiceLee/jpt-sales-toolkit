#!/usr/bin/env python3
"""Create or reset one leader account for testing a build.

Writes to the database the installed application actually opens, so the account
works in the packaged app rather than only when running from source:

    macOS    ~/Library/Application Support/JPT Sales Toolkit/data
    Windows  %LOCALAPPDATA%\\JPT Sales Toolkit\\data

Usage:
    python3 scripts/create_leader_account.py                    # installed app
    python3 scripts/create_leader_account.py --source           # ./data
    python3 scripts/create_leader_account.py --data-dir <path>
    python3 scripts/create_leader_account.py --username lead --password ...
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

ALPHABET = string.ascii_letters + string.digits


def readable_password(length: int = 16) -> str:
    """A password that survives being read aloud and retyped."""
    ambiguous = set("Il1O0")
    pool = [char for char in ALPHABET if char not in ambiguous]
    return "".join(secrets.choice(pool) for _ in range(length))


def resolve_data_dir(args) -> Path:
    if args.data_dir:
        return Path(args.data_dir).expanduser().resolve()
    if args.source:
        return ROOT_DIR / "data"
    from desktop_runtime.paths import user_data_dir

    return user_data_dir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir")
    parser.add_argument(
        "--source", action="store_true",
        help="use ./data, the directory used when running from source",
    )
    parser.add_argument("--username", default="qa_leader")
    parser.add_argument("--display-name", default="QA Leader")
    parser.add_argument("--password")
    args = parser.parse_args()

    data_dir = resolve_data_dir(args)
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["JPT_DATA_DIR"] = str(data_dir)

    from backend.config import init_settings
    from backend.repositories import close_db
    from backend.repositories.base import generate_uuid, get_db, now_iso
    from backend.services.password_service import hash_password
    from backend.startup_upgrade import initialize_database_safely

    settings = init_settings(ROOT_DIR)
    # Never create an account in a database that has not been safely brought to
    # the current schema: that is the same path the application takes on start.
    result = initialize_database_safely(settings)

    password = args.password or readable_password()
    conn = get_db()
    now = now_iso()
    existing = conn.execute(
        "SELECT id FROM users WHERE username = ?", (args.username,)
    ).fetchone()
    if existing:
        user_id = existing["id"]
        conn.execute(
            "UPDATE users SET password_hash = ?, display_name = ?, "
            "role = 'leader', is_active = 1 WHERE id = ?",
            (hash_password(password), args.display_name, user_id),
        )
        action = "reset"
    else:
        user_id = generate_uuid()
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, "
            "role, is_active, created_at) VALUES (?, ?, ?, ?, 'leader', 1, ?)",
            (user_id, args.username, hash_password(password),
             args.display_name, now),
        )
        action = "created"
    # The account needs a credential row in the same organization as everybody
    # else, not no credential at all: the team directory is read through that
    # membership, so an account without one sees only itself and cannot be
    # planned alongside colleagues.
    if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='user_credentials'"
    ).fetchone():
        organization = conn.execute(
            "SELECT organization_id FROM user_credentials WHERE is_active = 1 "
            "ORDER BY created_at LIMIT 1"
        ).fetchone()
        organization_id = (
            organization["organization_id"] if organization
            else conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()["id"]
        )
        conn.execute("DELETE FROM user_credentials WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO user_credentials (id, organization_id, user_id, "
            "password_hash, password_scheme, must_change_password, is_active, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'pbkdf2_sha256', 0, 1, ?, ?)",
            (generate_uuid(), organization_id, user_id,
             hash_password(password), now, now),
        )
    conn.commit()
    close_db()

    print(f"Leader account {action}.")
    print(f"  data directory : {data_dir}")
    print(f"  schema         : {result.source_schema_version} -> "
          f"{result.target_schema_version}"
          + (f" (migrated, backup {Path(result.backup_path).name})"
             if result.migrated and result.backup_path else ""))
    print(f"  username       : {args.username}")
    print(f"  password       : {password}")
    print(f"  role           : leader (full permissions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
