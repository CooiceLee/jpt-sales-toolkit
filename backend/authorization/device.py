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
    """Return one process-stable, privacy-preserving machine fingerprint.

    The hash and the identifier it is taken from are unchanged: a machine that
    was authorized before keeps the same fingerprint. What changed is what
    happens when the machine cannot be identified - see _platform_identifier.
    """
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


# Where the hardware identity is read from. Absolute, because the program is
# started from Finder, from a launcher and from a service manager, and each
# hands it a different PATH: found on one, missing on the next, and the machine
# would have looked like a different machine each time.
IOREG = "/usr/sbin/ioreg"
WINDOWS_CRYPTOGRAPHY_KEY = r"SOFTWARE\Microsoft\Cryptography"


class DeviceIdentityError(AuthorizationError):
    """This machine could not be identified.

    Not the same as "this machine is not authorized yet". An unidentified
    machine must stop and say so: the fallback that used to run here mixed
    uuid.getnode() into the identity, and that value is a *random* number
    whenever the hardware address cannot be read - so every start looked like a
    brand-new device and the authorization installed on this one silently
    stopped matching.
    """


def _windows_identifier() -> str:
    try:
        import winreg  # type: ignore
    except ImportError as error:                       # pragma: no cover - platform
        raise DeviceIdentityError(
            "This machine could not be identified: the Windows registry is "
            "not readable from this program."
        ) from error
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINDOWS_CRYPTOGRAPHY_KEY) as key:
            value = str(winreg.QueryValueEx(key, "MachineGuid")[0]).strip()
    except OSError as error:
        raise DeviceIdentityError(
            "This machine could not be identified: Windows did not return a "
            "MachineGuid. Run JPT as the signed-in user on this computer."
        ) from error
    if not value:
        raise DeviceIdentityError(
            "This machine could not be identified: the Windows MachineGuid is "
            "empty."
        )
    return value


def _darwin_identifier() -> str:
    try:
        output = subprocess.check_output(
            [IOREG, "-rd1", "-c", "IOPlatformExpertDevice"],
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired as error:
        raise DeviceIdentityError(
            "This machine could not be identified: reading the hardware id "
            "timed out. Try again, and report it if it keeps happening."
        ) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise DeviceIdentityError(
            "This machine could not be identified: the hardware id could not "
            f"be read ({IOREG})."
        ) from error
    for line in output.splitlines():
        if "IOPlatformUUID" in line:
            value = line.split("=", 1)[-1].strip().strip('"')
            if value:
                return value
    raise DeviceIdentityError(
        "This machine could not be identified: the hardware id was not in the "
        "system's answer."
    )


def _platform_identifier() -> str:
    system = platform.system().lower()
    if system == "windows":
        return _windows_identifier()
    if system == "darwin":
        return _darwin_identifier()
    # Everywhere else the machine name and architecture are what there is. They
    # are stable for a given installation, and unlike the old fallback nothing
    # random goes into them.
    value = f"{platform.node()}:{platform.machine()}"
    if value.strip(":"):
        return value
    raise DeviceIdentityError(
        "This machine could not be identified: no stable machine name is "
        "available."
    )
