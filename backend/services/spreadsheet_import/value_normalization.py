"""Normalize spreadsheet scalar values for SQLite constraints."""

from .persistence_common import CLEAR


def boolean_value(value) -> int:
    if value is CLEAR:
        return 0
    normalized = str(value).strip().casefold()
    if value in (True, 1) or normalized in {"true", "yes", "y", "1"}:
        return 1
    if value in (False, 0) or normalized in {"false", "no", "n", "0"}:
        return 0
    raise ValueError(f"Invalid boolean value: {value}")
