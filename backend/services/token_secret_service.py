"""Per-installation token secret management."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from ..config import get_settings


SECRET_FILENAME = "jwt_secret"


def get_token_secret() -> str:
    """Load or create a private JWT secret outside the application bundle."""
    override = os.environ.get("JPT_JWT_SECRET")
    if override:
        if len(override) < 32:
            raise ValueError("JPT_JWT_SECRET must contain at least 32 characters")
        return override

    settings = get_settings()
    secret_path = settings.runtime_config_dir / SECRET_FILENAME
    if secret_path.is_file():
        secret = secret_path.read_text(encoding="utf-8").strip()
        if len(secret) < 32:
            raise RuntimeError("Stored JWT secret is invalid")
        return secret

    return _create_secret(secret_path)


def _create_secret(secret_path: Path) -> str:
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    try:
        descriptor = os.open(
            secret_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        return secret_path.read_text(encoding="utf-8").strip()

    with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
        secret_file.write(secret)
    try:
        secret_path.chmod(0o600)
    except OSError:
        pass
    return secret
