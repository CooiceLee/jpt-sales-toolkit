"""Cross-platform single-instance lock, health polling and port selection."""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


_LOCAL_OPENER = build_opener(ProxyHandler({}))


class InstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> bool:
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, IOError):
            self.handle.close()
            self.handle = None
            return False

    def release(self) -> None:
        if not self.handle:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def find_available_port(preferred: int, attempts: int = 20) -> int:
    for port in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            try:
                candidate.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No local port is available for JPT Sales Toolkit")


def is_healthy(port: int, timeout: float = 0.5) -> bool:
    try:
        with _LOCAL_OPENER.open(
            f"http://127.0.0.1:{port}/api/health", timeout=timeout
        ) as response:
            value = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and value.get("status") == "ok"
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False


def wait_until_healthy(port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_healthy(port):
            return True
        time.sleep(0.2)
    return False


def write_instance_port(config_dir: Path, port: int) -> None:
    target = config_dir / "desktop_instance.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"port": port}), encoding="utf-8")
    os.replace(temporary, target)
    try:
        target.chmod(0o600)
    except OSError:
        pass


def read_instance_port(config_dir: Path) -> Optional[int]:
    try:
        value = json.loads((config_dir / "desktop_instance.json").read_text(encoding="utf-8"))
        port = int(value["port"])
        return port if 1 <= port <= 65535 else None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
