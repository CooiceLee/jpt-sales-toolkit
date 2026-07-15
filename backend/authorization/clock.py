"""Persist a monotonic wall-clock watermark for offline expiry checks."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import AuthorizationError, iso_utc, parse_utc


_LOCK = threading.Lock()
_STATE: dict[Path, tuple[datetime, datetime]] = {}
_ROLLBACK_TOLERANCE = timedelta(minutes=5)
_WRITE_INTERVAL = timedelta(minutes=1)


class AuthorizationClock:
    def __init__(self, config_dir: Path):
        self.path = config_dir / "authorization_clock.json"

    def check(self, now: datetime) -> datetime:
        current = _as_utc(now)
        with _LOCK:
            last_seen, last_written = _STATE.get(self.path, self._load())
            if current + _ROLLBACK_TOLERANCE < last_seen:
                raise AuthorizationError("System clock moved backwards; Leader recovery is required")
            newest = max(current, last_seen)
            if not self.path.exists() or newest - last_written >= _WRITE_INTERVAL:
                self._write(newest)
                last_written = newest
            _STATE[self.path] = (newest, last_written)
        return current

    def reset(self, now: datetime) -> None:
        """Reset the watermark after authenticated Leader recovery."""
        current = _as_utc(now)
        with _LOCK:
            self._write(current)
            _STATE[self.path] = (current, current)

    def _load(self) -> tuple[datetime, datetime]:
        if not self.path.exists():
            epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
            return epoch, epoch
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            last_seen = parse_utc(value["last_seen_at"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuthorizationError("Authorization clock state is invalid") from exc
        return last_seen, last_seen

    def _write(self, value: datetime) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        data = json.dumps({"last_seen_at": iso_utc(value)}).encode("utf-8")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        except OSError as exc:
            raise AuthorizationError("Authorization clock state could not be saved") from exc


def reset_authorization_clock_cache() -> None:
    """Clear process cache for tests and data-directory switches."""
    with _LOCK:
        _STATE.clear()


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AuthorizationError("Authorization clock requires timezone-aware UTC time")
    return value.astimezone(timezone.utc)
