"""
Application configuration - centralized settings management.

All services should get configuration through dependency injection,
not by importing globals directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip()

MAX_UPLOAD_SIZE = 25 * 1024 * 1024
ALLOWED_ATTACHMENT_MIME_TYPES = (
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "text/csv",
)
ATTACHMENT_CATEGORIES = (
    "email_original",
    "quotation",
    "report",
    "test_result",
    "screenshot",
    "other",
)


@dataclass
class AppSettings:
    """Application-wide settings."""

    app_root: Path
    data_dir: Path
    config_dir: Path
    runtime_config_dir: Path
    db_path: Path
    upload_dir: Path
    backup_dir: Path

    # Attachment constraints
    max_upload_size: int = MAX_UPLOAD_SIZE
    allowed_mime_types: tuple = ALLOWED_ATTACHMENT_MIME_TYPES
    allowed_categories: tuple = ATTACHMENT_CATEGORIES


# Singleton instance - initialized by app startup
_settings: Optional[AppSettings] = None


def init_settings(app_root: Optional[Path] = None) -> AppSettings:
    """Initialize application settings."""
    global _settings

    if app_root is None:
        app_root = Path(__file__).parent.parent

    env_data_dir = os.environ.get("JPT_DATA_DIR")
    data_dir = Path(env_data_dir).expanduser() if env_data_dir else app_root / "data"

    _settings = AppSettings(
        app_root=app_root,
        data_dir=data_dir,
        config_dir=app_root / "config",
        runtime_config_dir=data_dir / "config",
        db_path=data_dir / "database.sqlite",
        upload_dir=data_dir / "attachments",
        backup_dir=data_dir / "backups",
    )

    # Ensure directories exist
    _settings.data_dir.mkdir(parents=True, exist_ok=True)
    _settings.upload_dir.mkdir(parents=True, exist_ok=True)
    _settings.backup_dir.mkdir(parents=True, exist_ok=True)
    _settings.runtime_config_dir.mkdir(parents=True, exist_ok=True)

    return _settings


def get_settings() -> AppSettings:
    """Get application settings (must be initialized first)."""
    if _settings is None:
        raise RuntimeError("Settings not initialized. Call init_settings() first.")
    return _settings
