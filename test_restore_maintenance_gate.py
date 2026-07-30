"""Concurrency regression for online full-database restore."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app_v2 import create_app
from backend.database_access import database_access_gate
from backend.repositories import (
    UserCredentialRepository,
    UserRepository,
    close_db,
    get_db,
)
from backend.services.admin_service import AdminService


PASSWORD = "RestoreGate2026!"


def wait_until(predicate, label: str, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {label}")


def add_probe_route(app, path: str, endpoint) -> None:
    """Insert a test route before the application's SPA catch-all route."""
    app.add_api_route(path, endpoint, methods=["GET"])
    app.router.routes.insert(0, app.router.routes.pop())


def seed_leader() -> None:
    password_hash = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()
    user_id = UserRepository().create(
        "gate.leader", password_hash, "Gate Leader", "leader", "EU",
    )
    UserCredentialRepository().create({
        "user_id": user_id,
        "password_hash": password_hash,
        "password_scheme": "legacy_sha256",
        "must_change_password": False,
    })


def run_request(results: dict, name: str, request) -> None:
    try:
        results[name] = request()
    except BaseException as exc:  # Preserve worker failures for the main thread.
        results[name] = exc


def test_restore_drains_requests_and_reopens_database() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_restore_gate_") as directory:
        data_dir = Path(directory) / "data"
        hold_started = threading.Event()
        release_hold = threading.Event()
        restore_entered = threading.Event()
        release_restore = threading.Event()
        probe_entered = threading.Event()

        async def hold_request():
            hold_started.set()
            await asyncio.to_thread(release_hold.wait)
            value = get_db().execute("SELECT value FROM maintenance_probe").fetchone()[0]
            return {"value": value}

        async def probe_request():
            probe_entered.set()
            connection = get_db()
            value = connection.execute(
                "SELECT value FROM maintenance_probe"
            ).fetchone()[0]
            return {"value": value, "connection_id": id(connection)}

        close_db()
        with patch.dict(os.environ, {"JPT_DATA_DIR": str(data_dir)}):
            app = create_app()
            add_probe_route(app, "/api/_test/hold", hold_request)
            add_probe_route(app, "/api/_test/probe", probe_request)
            with TestClient(app) as lifecycle_client:
                seed_leader()
                login = lifecycle_client.post("/api/auth/login", json={
                    "username": "gate.leader",
                    "password": PASSWORD,
                })
                assert login.status_code == 200, login.text
                headers = {"Authorization": f"Bearer {login.json()['token']}"}

                old_connection = get_db()
                old_connection.execute(
                    "CREATE TABLE maintenance_probe (value TEXT NOT NULL)"
                )
                old_connection.execute(
                    "INSERT INTO maintenance_probe (value) VALUES ('new')"
                )
                old_connection.commit()
                service = AdminService(data_dir=data_dir)
                archive = Path(service.backup(
                    data_dir.parent / "exports", "leader", apply_retention=False,
                )["backup_path"])
                old_connection.execute("UPDATE maintenance_probe SET value = 'old'")
                old_connection.commit()

                hold_client, restore_client, probe_client = (
                    TestClient(app), TestClient(app), TestClient(app)
                )
                results: dict = {}
                original_restore = AdminService.restore

                def controlled_restore(self, *args, **kwargs):
                    restore_entered.set()
                    if not release_restore.wait(5):
                        raise AssertionError("restore test release was not signaled")
                    return original_restore(self, *args, **kwargs)

                threads = []
                try:
                    with patch.object(AdminService, "restore", controlled_restore):
                        threads.append(threading.Thread(
                            target=run_request,
                            args=(results, "hold", lambda: hold_client.get("/api/_test/hold")),
                        ))
                        threads[-1].start()
                        assert hold_started.wait(5), "ordinary request did not start"

                        payload = archive.read_bytes()
                        threads.append(threading.Thread(
                            target=run_request,
                            args=(results, "restore", lambda: restore_client.post(
                                "/api/admin/restore", headers=headers,
                                files={"backup_file": ("backup.zip", payload, "application/zip")},
                            )),
                        ))
                        threads[-1].start()
                        wait_until(
                            lambda: database_access_gate.waiting_writers == 1,
                            "queued restore writer",
                        )

                        threads.append(threading.Thread(
                            target=run_request,
                            args=(results, "probe", lambda: probe_client.get("/api/_test/probe")),
                        ))
                        threads[-1].start()
                        time.sleep(0.1)
                        assert not probe_entered.is_set(), "reader bypassed a queued restore"

                        release_hold.set()
                        assert restore_entered.wait(5), "restore did not acquire exclusive access"
                        assert not probe_entered.is_set(), "reader entered during restore"
                        release_restore.set()

                        for thread in threads:
                            thread.join(15)
                            assert not thread.is_alive(), "request thread did not finish"
                finally:
                    release_hold.set()
                    release_restore.set()
                    for thread in threads:
                        thread.join(1)
                    hold_client.close()
                    restore_client.close()
                    probe_client.close()

                for name in ("hold", "restore", "probe"):
                    assert not isinstance(results.get(name), BaseException), results.get(name)
                    assert results[name].status_code == 200, results[name].text
                assert results["hold"].json()["value"] == "old"
                assert results["probe"].json()["value"] == "new"
                reopened = get_db()
                assert reopened is not old_connection
                assert reopened.execute(
                    "SELECT value FROM maintenance_probe"
                ).fetchone()[0] == "new"
                assert lifecycle_client.get("/api/health").status_code == 200
        close_db()


if __name__ == "__main__":
    test_restore_drains_requests_and_reopens_database()
    print("PASS: restore maintenance gate drains, excludes, and reopens")
