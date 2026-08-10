"""Primitive validation shared by the offline Tech task package contract."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Iterable


class PackageValidationError(ValueError):
    """Safe validation failure suitable for a preflight issue."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require_strings(source: dict, fields: Iterable[str], code: str) -> None:
    invalid = sorted(
        field
        for field in fields
        if not isinstance(source.get(field), str) or not source[field].strip()
    )
    if invalid:
        raise PackageValidationError(
            code, f"Fields must be non-empty strings: {', '.join(invalid)}"
        )


def validate_optional_string(source: dict, field: str, code: str) -> None:
    value = source.get(field)
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise PackageValidationError(code, f"{field} must be a non-empty string or null")


def validate_timestamp(value: Any) -> None:
    if not isinstance(value, str):
        raise PackageValidationError("invalid_created_at", "created_at must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PackageValidationError(
            "invalid_created_at", "created_at must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise PackageValidationError(
            "invalid_created_at", "created_at must include a timezone"
        )


def validate_digest(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PackageValidationError(
            "invalid_package_digest", "payload_sha256 must be a lowercase SHA-256 digest"
        )


def validate_scalar_mapping(value: Any, code: str, label: str) -> None:
    if not isinstance(value, dict):
        raise PackageValidationError(code, f"{label} must be an object")
    invalid = [key for key, item in value.items() if not _is_json_scalar(item)]
    if invalid:
        raise PackageValidationError(
            code, f"{label} fields must contain scalar values: {', '.join(sorted(invalid))}"
        )


def _is_json_scalar(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, int):
        return -(2**63) <= value < 2**63
    return isinstance(value, float) and math.isfinite(value)
