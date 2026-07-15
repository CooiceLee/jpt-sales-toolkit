"""Cross-platform device request generation with hashed machine identity."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import uuid
from functools import lru_cache
from typing import Optional

from .common import AuthorizationError, iso_utc, utc_now


REQUEST_FORMAT = "jpt-device-request"
REQUEST_VERSION = 1


@lru_cache(maxsize=1)
def device_fingerprint() -> str:
    """Return one process-stable, privacy-preserving machine fingerprint."""
    raw = _platform_identifier()
    return hashlib.sha256(f"jpt-device-v1:{raw}".encode("utf-8")).hexdigest()


def build_device_request(device_name: Optional[str] = None) -> dict:
    request = {
        "format": REQUEST_FORMAT,
        "version": REQUEST_VERSION,
        "request_id": str(uuid.uuid4()),
        "device_id": device_fingerprint(),
        "device_name": device_name or platform.node() or "JPT device",
        "platform": platform.system().lower() or "unknown",
        "created_at": iso_utc(utc_now()),
    }
    return validate_device_request(request)


def validate_device_request(request: dict) -> dict:
    if request.get("format") != REQUEST_FORMAT or request.get("version") != REQUEST_VERSION:
        raise AuthorizationError("Unsupported device request format")
    required = ("request_id", "device_id", "device_name", "platform", "created_at")
    if any(not request.get(field) for field in required):
        raise AuthorizationError("Device request is incomplete")
    device_id = str(request["device_id"])
    if len(device_id) != 64 or any(char not in "0123456789abcdef" for char in device_id.lower()):
        raise AuthorizationError("Device request fingerprint is invalid")
    return dict(request)


def _platform_identifier() -> str:
    system = platform.system().lower()
    if system == "windows":
        try:
            import winreg  # type: ignore

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except (ImportError, OSError):
            pass
    if system == "darwin":
        try:
            output = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True,
                timeout=2,
            )
            for line in output.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=", 1)[-1].strip().strip('"')
        except (OSError, subprocess.SubprocessError):
            pass
    return f"{platform.node()}:{uuid.getnode()}:{platform.machine()}"
