"""Platform-owned writable paths and launcher logging."""

from __future__ import annotations

import logging
import os
import platform
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


APP_DIRECTORY = "JPT Sales Toolkit"


def user_data_dir(override: Optional[str] = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system().lower()
    if system == "windows":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif system == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_DIRECTORY / "data"


def prepare_data_dir(path: Path) -> None:
    for directory in (path, path / "config", path / "logs"):
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.chmod(0o700)
        except OSError:
            pass


def configure_logging(data_dir: Path) -> logging.Logger:
    logger = logging.getLogger("jpt.desktop")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            data_dir / "logs" / "launcher.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
