"""Low-level strict validators shared by authorization package policies."""

from __future__ import annotations

import base64
import binascii
import uuid
from typing import Any

from .common import AuthorizationError


def decode_base64url(value: Any, expected_bytes: int, label: str) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise AuthorizationError(f"{label} is invalid")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError, TypeError) as exc:
        raise AuthorizationError(f"{label} is invalid") from exc
    canonical = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    if len(raw) != expected_bytes or canonical != value:
        raise AuthorizationError(f"{label} is invalid")
    return raw


def require_dict(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise AuthorizationError(f"{label} must be an object")


def require_exact_fields(value: dict, fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise AuthorizationError(f"{label} fields are invalid")


def require_non_empty_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AuthorizationError(f"{label} must be non-empty text")


def require_lower_hex(value: Any, length: int, label: str) -> None:
    if not isinstance(value, str) or len(value) != length:
        raise AuthorizationError(f"{label} is invalid")
    if value != value.lower() or any(char not in "0123456789abcdef" for char in value):
        raise AuthorizationError(f"{label} is invalid")


def require_uuid(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise AuthorizationError(f"{label} is invalid")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise AuthorizationError(f"{label} is invalid") from exc
    if str(parsed) != value:
        raise AuthorizationError(f"{label} is invalid")
