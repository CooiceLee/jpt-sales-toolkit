"""A cancelled restore request must retain exclusive database access."""

from __future__ import annotations

import asyncio
import io
import tempfile
import threading
import time
from pathlib import Path

from fastapi import UploadFile

from backend.database_access import DatabaseAccessGate
from backend.routers.admin import restore_backup


class BlockingRestoreService:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.started = threading.Event()
        self.release = threading.Event()

    def validate_backup_archive(self, _path: Path) -> dict:
        return {}

    def restore(self, _path: Path, _actor_id: str) -> dict:
        self.started.set()
        if not self.release.wait(5):
            raise AssertionError("restore worker was not released")
        return {}


async def wait_thread_event(event: threading.Event, label: str) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if event.is_set():
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"Timed out waiting for {label}")


async def run_regression() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_cancel_restore_") as directory:
        data_dir = Path(directory) / "data"
        data_dir.mkdir()
        service = BlockingRestoreService(data_dir)
        gate = DatabaseAccessGate()
        upload = UploadFile(file=io.BytesIO(b"test archive"), filename="backup.zip")
        probe_entered = asyncio.Event()

        async def request() -> None:
            async with gate.exclusive():
                await restore_backup(
                    backup_file=upload,
                    user={"id": "leader"},
                    service=service,
                )

        async def probe() -> None:
            async with gate.shared():
                probe_entered.set()

        request_task = asyncio.create_task(request())
        await wait_thread_event(service.started, "restore worker")
        request_task.cancel()
        await asyncio.sleep(0.02)
        request_task.cancel()  # Repeated disconnect cancellation is also safe.
        probe_task = asyncio.create_task(probe())
        await asyncio.sleep(0.05)

        staging_dir = data_dir / ".restore_uploads"
        assert not request_task.done(), "cancel released the request before restore ended"
        assert not probe_entered.is_set(), "probe entered while restore worker was active"
        assert len(list(staging_dir.glob("*"))) == 1

        service.release.set()
        try:
            await request_task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("cancelled restore request returned normally")
        await asyncio.wait_for(probe_task, 1)

        assert probe_entered.is_set()
        assert gate.is_idle
        assert not staging_dir.exists()
        assert upload.file.closed


def test_cancelled_restore_keeps_gate_until_worker_finishes() -> None:
    asyncio.run(run_regression())


if __name__ == "__main__":
    test_cancelled_restore_keeps_gate_until_worker_finishes()
    print("PASS: cancelled restore retains gate and cleans staging")
