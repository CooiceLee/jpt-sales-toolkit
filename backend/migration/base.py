"""
Base utilities for migration scripts.
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


def now_iso() -> str:
    """Return current timestamp in ISO format."""
    return datetime.utcnow().isoformat()


def normalize_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""
    return name.lower().strip().replace(",", "").replace(".", "")


def extract_domain(email: str) -> Optional[str]:
    """Extract domain from email address."""
    if not email or "@" not in email:
        return None
    return email.split("@")[-1].lower().strip()


def hash_password(password: str) -> str:
    """Hash password using SHA-256. MVP only - use bcrypt in production."""
    return hashlib.sha256(password.encode()).hexdigest()


def safe_numeric(value: Any) -> Optional[float]:
    """Safely convert value to numeric, return None if invalid."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_date(value: Any) -> Optional[str]:
    """Validate and return ISO date string, or None if invalid."""
    if not value or not isinstance(value, str):
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except ValueError:
        return None


def empty_to_none(value: Any) -> Any:
    """Convert empty strings to None."""
    if value == "":
        return None
    return value


class MigrationContext:
    """Holds migration state and connections."""

    def __init__(
        self,
        legacy_data_dir: Path,
        output_db_path: Path,
        dry_run: bool = False,
    ):
        self.legacy_data_dir = legacy_data_dir
        self.output_db_path = output_db_path
        self.dry_run = dry_run

        self.legacy_user_map: dict[str, dict] = {}
        self.legacy_id_map: dict[str, str] = {}
        self.customer_map: dict[str, str] = {}  # normalized_name -> customer_id
        self.domain_map: dict[str, str] = {}    # domain -> customer_id
        self.email_map: dict[str, str] = {}     # email -> customer_id

        self.warnings: list[dict] = []
        self.stats = {
            "users_created": 0,
            "customers_created": 0,
            "leads_created": 0,
            "activities_created": 0,
            "pre_sales_tasks_created": 0,
            "after_sales_tasks_created": 0,
        }

        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database connection not initialized")
        return self._conn

    def open_db(self) -> None:
        """Open database connection."""
        if self.dry_run:
            self._conn = sqlite3.connect(":memory:")
        else:
            self._conn = sqlite3.connect(str(self.output_db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def close_db(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def add_warning(self, legacy_id: str, field: str, warning_type: str, raw_value: Any) -> None:
        """Record a migration warning."""
        self.warnings.append({
            "legacy_inquiry_id": legacy_id,
            "field": field,
            "warning": warning_type,
            "raw_value": str(raw_value)[:200],
        })

    def load_legacy_inquiries(self) -> list[dict]:
        """Load all legacy inquiry JSON files."""
        inquiries = []
        inquiries_dir = self.legacy_data_dir / "inquiries"
        if not inquiries_dir.exists():
            return inquiries

        for month_dir in inquiries_dir.iterdir():
            if not month_dir.is_dir():
                continue
            for json_file in month_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        data["_source_file"] = str(json_file)
                        inquiries.append(data)
                except Exception as e:
                    self.add_warning(
                        json_file.name,
                        "_source_file",
                        "file_read_error",
                        str(e),
                    )
        return inquiries

    def load_legacy_config(self, filename: str) -> dict:
        """Load a legacy config JSON file."""
        config_dir = self.legacy_data_dir.parent / "config"
        config_file = config_dir / filename
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def generate_report(self) -> dict:
        """Generate final migration report."""
        return {
            "migration_time": now_iso(),
            "dry_run": self.dry_run,
            "stats": self.stats,
            "warnings": self.warnings,
            "legacy_user_map": self.legacy_user_map,
            "legacy_id_map": self.legacy_id_map,
        }
