#!/usr/bin/env python3
"""Frozen desktop entry point for the local JPT web application."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from desktop_runtime.instance import (
    InstanceLock,
    find_available_port,
    read_instance_health,
    read_instance_port,
    wait_until_healthy,
    write_instance_port,
)
from desktop_runtime.paths import configure_logging, prepare_data_dir, user_data_dir


APP_ROOT = Path(__file__).resolve().parent
APP_VERSION = (APP_ROOT / "VERSION").read_text(encoding="utf-8").strip()
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JPT Sales Toolkit desktop launcher")
    parser.add_argument("--data-dir", help="Override writable data directory")
    parser.add_argument("--port", type=int, default=8765, help="Preferred loopback port")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    return parser.parse_args()


def open_when_ready(port: int, logger) -> None:
    if wait_until_healthy(port):
        webbrowser.open(f"http://127.0.0.1:{port}")
    else:
        logger.error("Server did not become healthy on port %s", port)


def running_from_disk_image() -> bool:
    """Detect a read-only macOS disk image, including custom CI mount points."""
    if sys.platform != "darwin":
        return False
    executable = str(Path(sys.executable))
    if executable.startswith("/Volumes/"):
        return True
    try:
        read_only = getattr(os, "ST_RDONLY", 1)
        return bool(os.statvfs(executable).f_flag & read_only)
    except OSError:
        return False


def instance_version_mismatch(status: dict | None) -> bool:
    running = str((status or {}).get("version") or "").strip()
    return running != APP_VERSION


def show_instance_version_warning(status: dict, logger) -> None:
    running = str(status.get("version") or "an older version")
    message = (
        f"JPT {running} is still running. Quit it completely, then launch "
        f"JPT {APP_VERSION} again. On macOS, eject the JPT disk image and "
        "open JPT from Applications."
    )
    logger.error(message)
    if sys.platform == "darwin":
        script = (
            'on run argv\n'
            'display alert "JPT update waiting" message (item 1 of argv) '
            'as warning buttons {"OK"} default button "OK"\n'
            'end run'
        )
        try:
            subprocess.run(["osascript", "-e", script, message], check=False, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            logger.exception("Unable to show the macOS version warning")
    elif sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "JPT update waiting", 0x30)
        except (AttributeError, OSError):
            logger.exception("Unable to show the Windows version warning")


def main() -> int:
    multiprocessing.freeze_support()
    args = arguments()
    data_dir = user_data_dir(args.data_dir)
    prepare_data_dir(data_dir)
    os.environ["JPT_DATA_DIR"] = str(data_dir)
    os.environ["JPT_DESKTOP"] = "1"
    os.environ["JPT_RUNNING_FROM_DISK_IMAGE"] = "1" if running_from_disk_image() else "0"
    logger = configure_logging(data_dir)
    lock = InstanceLock(data_dir / "config" / "desktop.lock")
    if not lock.acquire():
        running_port = read_instance_port(data_dir / "config")
        if running_port and wait_until_healthy(running_port, timeout=10):
            status = read_instance_health(running_port) or {}
            if instance_version_mismatch(status):
                show_instance_version_warning(status, logger)
                return 2
            if not args.no_browser:
                webbrowser.open(f"http://127.0.0.1:{running_port}")
            return 0
        logger.error("Another instance owns the data directory but is not healthy")
        return 1

    try:
        port = find_available_port(args.port)
        write_instance_port(data_dir / "config", port)
        from backend.app_v2 import create_app
        import uvicorn

        if not args.no_browser:
            threading.Thread(
                target=open_when_ready, args=(port, logger), daemon=True
            ).start()
        logger.info("Starting JPT Sales Toolkit at http://127.0.0.1:%s", port)
        app = create_app()
        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=port,
            log_level="info", log_config=None, access_log=False,
        ))
        app.state.desktop_shutdown = lambda: setattr(server, "should_exit", True)
        server.run()
        return 0
    except Exception:
        logger.exception("JPT Sales Toolkit failed to start")
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
