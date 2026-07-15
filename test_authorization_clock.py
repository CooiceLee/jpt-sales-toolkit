"""Offline clock rollback detection and persistence contract."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.authorization.clock import AuthorizationClock, reset_authorization_clock_cache
from backend.authorization.common import AuthorizationError


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_auth_clock_") as temp_dir:
        config_dir = Path(temp_dir)
        start = datetime(2026, 7, 14, 8, 0, tzinfo=timezone.utc)
        clock = AuthorizationClock(config_dir)
        assert clock.check(start) == start
        state_file = config_dir / "authorization_clock.json"
        assert state_file.is_file()
        assert clock.check(start + timedelta(minutes=2)) == start + timedelta(minutes=2)

        reset_authorization_clock_cache()
        restarted = AuthorizationClock(config_dir)
        try:
            restarted.check(start - timedelta(days=1))
        except AuthorizationError as exc:
            assert "backwards" in str(exc).lower()
        else:
            raise AssertionError("Clock rollback was not rejected")

        state_file.write_text("not-json", encoding="utf-8")
        reset_authorization_clock_cache()
        try:
            AuthorizationClock(config_dir).check(start)
        except AuthorizationError as exc:
            assert "invalid" in str(exc).lower()
        else:
            raise AssertionError("Corrupt clock state was not rejected")
    reset_authorization_clock_cache()
    print("PASS: offline authorization clock rollback detection")


if __name__ == "__main__":
    main()
