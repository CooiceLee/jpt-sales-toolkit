"""API regressions for bounded, isolated backup restore uploads."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.repositories import UserCredentialRepository, UserRepository, close_db
from backend.services.admin_service import AdminService


PASSWORD = "RestoreSecurity2026!"


def expect(response, status_code: int, label: str):
    assert response.status_code == status_code, (
        f"{label}: expected HTTP {status_code}, got {response.status_code}; "
        f"body={response.text[:500]}"
    )
    return response


def seed_leader() -> str:
    password_hash = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()
    user_id = UserRepository().create(
        "restore.leader", password_hash, "Restore Leader", "leader", "EU",
    )
    UserCredentialRepository().create({
        "user_id": user_id,
        "password_hash": password_hash,
        "password_scheme": "legacy_sha256",
        "must_change_password": False,
    })
    return user_id


def login(client: TestClient) -> dict[str, str]:
    response = expect(client.post("/api/auth/login", json={
        "username": "restore.leader",
        "password": PASSWORD,
    }), 200, "leader login")
    return {"Authorization": f"Bearer {response.json()['token']}"}


def assert_rejected_upload_cannot_overwrite(
    client: TestClient,
    headers: dict,
    data_dir: Path,
) -> None:
    backup_dir = data_dir / "backups"
    existing = backup_dir / "protected.zip"
    existing.write_bytes(b"keep-this-backup")
    escaped = data_dir.parent / "escaped.zip"
    escaped.unlink(missing_ok=True)
    database_hash = hashlib.sha256((data_dir / "database.sqlite").read_bytes()).hexdigest()

    response = expect(client.post(
        "/api/admin/restore",
        headers=headers,
        files={"backup_file": ("../../protected.zip", b"not a zip", "application/zip")},
    ), 400, "invalid traversal-named archive is rejected")
    assert response.json()["detail"]
    assert existing.read_bytes() == b"keep-this-backup"
    assert not escaped.exists()
    assert hashlib.sha256((data_dir / "database.sqlite").read_bytes()).hexdigest() == database_hash
    assert not list(backup_dir.glob("backup_*.zip")), "validation must precede pre-restore backup"
    assert not list((data_dir / ".restore_uploads").glob("*"))


def assert_upload_size_is_bounded(
    client: TestClient,
    headers: dict,
    data_dir: Path,
) -> None:
    with patch("backend.routers.admin.MAX_BACKUP_UPLOAD_SIZE", 32):
        expect(client.post(
            "/api/admin/restore",
            headers=headers,
            files={"backup_file": ("large.zip", b"x" * 33, "application/zip")},
        ), 413, "oversized backup is rejected")
    assert not list((data_dir / ".restore_uploads").glob("*"))


def assert_valid_upload_restores_from_staging(
    client: TestClient,
    headers: dict,
    data_dir: Path,
    actor_id: str,
) -> None:
    export_dir = data_dir.parent / "exports"
    result = AdminService(data_dir=data_dir).backup(
        export_dir,
        actor_id,
        apply_retention=False,
    )
    archive = Path(result["backup_path"])
    response = expect(client.post(
        "/api/admin/restore",
        headers=headers,
        files={"backup_file": ("../../replace-existing.zip", archive.read_bytes(), "application/zip")},
    ), 200, "valid staged backup restores")
    assert response.json()["source_backup"] == "uploaded backup"
    assert not (data_dir / "backups" / "replace-existing.zip").exists()
    assert not list((data_dir / ".restore_uploads").glob("*"))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_restore_upload_security_") as directory:
        data_dir = Path(directory) / "data"
        close_db()
        with patch.dict("os.environ", {"JPT_DATA_DIR": str(data_dir)}):
            try:
                with TestClient(create_app()) as client:
                    actor_id = seed_leader()
                    headers = login(client)
                    assert_rejected_upload_cannot_overwrite(client, headers, data_dir)
                    assert_upload_size_is_bounded(client, headers, data_dir)
                    assert_valid_upload_restores_from_staging(
                        client, headers, data_dir, actor_id,
                    )
            finally:
                close_db()
    print("PASS: backup restore uploads are bounded, isolated, validated, and cleaned")


if __name__ == "__main__":
    main()
