"""A changed password is the one that signs in afterwards.

Signing in reads the credential row when there is one, and the user row only
when there is not. A password change that wrote to the user row alone changed
nothing anybody could sign in with: the old password kept working, the new one
never did, and the account looked lost.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import init_settings
from backend.repositories import close_db, get_db, init_db
from backend.repositories.base import generate_uuid, now_iso
from backend.services.auth_service import AuthService
from backend.services.password_service import hash_password


def legacy_hash(password: str) -> str:
    """The pre-PBKDF2 shape a database can still be sitting on."""
    import hashlib

    return hashlib.sha256(password.encode("utf-8")).hexdigest()

OLD = "OldPassword123"
NEW = "NewPassword456"


def _service(temp: Path):
    """A fresh installation in a directory of its own."""
    close_db()
    settings = init_settings(temp / "app")
    settings.data_dir = temp
    settings.db_path = temp / "database.sqlite"
    settings.upload_dir = temp / "attachments"
    settings.backup_dir = temp / "backups"
    settings.runtime_config_dir = temp / "config"
    settings.runtime_config_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)
    return AuthService(), get_db()


def _seed(conn, *, with_credential: bool, legacy: bool = False) -> str:
    """One leader, with or without a credential row of their own."""
    user_id = generate_uuid()
    stored = legacy_hash(OLD) if legacy else hash_password(OLD)
    conn.execute(
        "INSERT INTO users (id, username, password_hash, display_name, role, "
        "is_active, created_at) VALUES (?, 'lead', ?, 'Lead', 'leader', 1, ?)",
        (user_id, stored, now_iso()),
    )
    if with_credential:
        organization = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()
        conn.execute(
            "INSERT INTO user_credentials (id, organization_id, user_id, "
            "password_hash, password_scheme, must_change_password, is_active, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?)",
            (generate_uuid(), organization["id"], user_id, stored,
             "legacy_sha256" if legacy else "pbkdf2_sha256", now_iso(), now_iso()),
        )
    conn.commit()
    return user_id


def check_the_new_password_is_the_one_that_works() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_pw_") as temp:
        auth, conn = _service(Path(temp))
        user_id = _seed(conn, with_credential=True)

        assert auth.change_password(user_id, OLD, NEW) is True
        assert auth.login("lead", NEW), (
            "the password that was just set does not sign in, so the account "
            "looks lost to whoever changed it"
        )
        assert auth.login("lead", OLD) is None, (
            "the old password still signs in after being changed"
        )
        # Both places agree, so nothing depends on which one is read.
        row = conn.execute(
            "SELECT u.password_hash AS user_hash, c.password_hash AS cred_hash "
            "FROM users u JOIN user_credentials c ON c.user_id = u.id "
            "WHERE u.id = ?", (user_id,)
        ).fetchone()
        assert row["user_hash"] == row["cred_hash"], (
            "the two places a password is kept disagree, so which one signs in "
            "depends on a fallback nobody can see"
        )
        close_db()


def check_an_account_without_a_credential_still_changes() -> None:
    """The older shape - no credential row - keeps working and gains one."""
    with tempfile.TemporaryDirectory(prefix="jpt_pw_nocred_") as temp:
        auth, conn = _service(Path(temp))
        user_id = _seed(conn, with_credential=False)
        assert auth.login("lead", OLD), "the fallback to the user row is gone"
        assert auth.change_password(user_id, OLD, NEW) is True
        assert auth.login("lead", NEW)
        assert conn.execute(
            "SELECT COUNT(*) FROM user_credentials WHERE user_id = ?", (user_id,)
        ).fetchone()[0] == 1
        close_db()


def check_a_legacy_hash_is_upgraded_once_and_stays_upgraded() -> None:
    """Signing in with an old-style hash rewrites it, rather than every time."""
    with tempfile.TemporaryDirectory(prefix="jpt_pw_legacy_") as temp:
        auth, conn = _service(Path(temp))
        user_id = _seed(conn, with_credential=True, legacy=True)

        assert auth.login("lead", OLD), "a legacy password stopped signing in"
        upgraded = conn.execute(
            "SELECT password_hash, password_scheme FROM user_credentials "
            "WHERE user_id = ?", (user_id,)
        ).fetchone()
        assert upgraded["password_scheme"] == "pbkdf2_sha256", (
            f"the credential was left on {upgraded['password_scheme']}, so every "
            "sign-in re-hashes it and none of them stick"
        )
        assert not upgraded["password_hash"].startswith(legacy_hash(OLD)[:16])

        assert auth.login("lead", OLD), "the upgraded hash no longer matches"
        again = conn.execute(
            "SELECT password_hash FROM user_credentials WHERE user_id = ?",
            (user_id,)
        ).fetchone()["password_hash"]
        assert again == upgraded["password_hash"], (
            "the credential is rewritten on every sign-in"
        )
        close_db()


def run() -> None:
    try:
        check_the_new_password_is_the_one_that_works()
        check_an_account_without_a_credential_still_changes()
        check_a_legacy_hash_is_upgraded_once_and_stays_upgraded()
        print("PASS: a changed password is the one that signs in afterwards")
    finally:
        close_db()


if __name__ == "__main__":
    run()
