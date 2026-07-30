"""Disposable sidecar cache; never mutates the business database."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path


class GeocodeCache:
    def __init__(self, path: Path, ttl_seconds: int = 60 * 60 * 24 * 60) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self._init_lock = threading.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        if not self._initialized:
            with self._init_lock:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS geocode_cache (
                        cache_key TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        expires_at INTEGER NOT NULL
                    )"""
                )
                conn.commit()
                self._initialized = True
        return conn

    def get(self, key: str) -> dict | None:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM geocode_cache WHERE cache_key = ? AND expires_at > ?",
                (key, now),
            ).fetchone()
            conn.execute("DELETE FROM geocode_cache WHERE expires_at <= ?", (now,))
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None

    def set(self, key: str, payload: dict, *, ttl_seconds: int | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        expires_at = int(time.time()) + max(1, ttl)
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO geocode_cache(cache_key, payload_json, expires_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(cache_key) DO UPDATE SET
                       payload_json = excluded.payload_json,
                       expires_at = excluded.expires_at""",
                (key, serialized, expires_at),
            )
