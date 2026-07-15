#!/usr/bin/env python3
"""Launch a frozen desktop build and verify its offline first-run endpoints."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener


LOCAL_OPENER = build_opener(ProxyHandler({}))
EXPECTED_VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text(
    encoding="utf-8"
).strip()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as value:
        value.bind(("127.0.0.1", 0))
        return int(value.getsockname()[1])


def fetch(url: str, method: str = "GET", payload=None, token: str | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    with LOCAL_OPENER.open(request, timeout=5) as response:
        return response.status, response.headers, response.read()


def wait_for_health(base_url: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            status, _, body = fetch(f"{base_url}/api/health")
            health = json.loads(body)
            if (
                status == 200
                and health["status"] == "ok"
                and health["version"] == EXPECTED_VERSION
                and health["desktop"] is True
            ):
                return
        except Exception as exc:  # process startup produces several expected failures
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Frozen application did not become healthy: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve()
    assert executable.is_file(), f"Frozen executable not found: {executable}"
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="jpt_frozen_smoke_") as temp_dir:
        process = subprocess.Popen([
            str(executable), "--no-browser", "--port", str(port),
            "--data-dir", temp_dir,
        ])
        try:
            base_url = f"http://127.0.0.1:{port}"
            wait_for_health(base_url)
            status, _, body = fetch(f"{base_url}/api/authorization/status")
            authorization = json.loads(body)
            assert status == 200 and authorization["mode"] == "setup"
            status, headers, body = fetch(
                f"{base_url}/api/authorization/device-request", method="POST"
            )
            request_payload = json.loads(body)
            assert status == 200 and request_payload["format"] == "jpt-device-request"
            assert ".jptreq" in headers.get("Content-Disposition", "")
            status, _, _ = fetch(
                f"{base_url}/api/authorization/bootstrap",
                method="POST",
                payload={
                    "username": "smoke.leader",
                    "display_name": "Smoke Leader",
                    "password": "Smoke-Login-2026!",
                    "issuer_passphrase": "Smoke-Issuer-Passphrase-2026!",
                },
            )
            assert status == 201
            status, _, body = fetch(
                f"{base_url}/api/auth/login",
                method="POST",
                payload={"username": "smoke.leader", "password": "Smoke-Login-2026!"},
            )
            token = json.loads(body)["token"]
            assert status == 200 and token
            status, _, body = fetch(
                f"{base_url}/api/desktop/shutdown", method="POST", token=token
            )
            assert status == 200 and json.loads(body)["status"] == "shutting_down"
            assert process.wait(timeout=10) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    print(f"PASS: frozen desktop smoke test ({executable.name})")


if __name__ == "__main__":
    main()
