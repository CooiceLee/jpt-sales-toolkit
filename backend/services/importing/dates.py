"""Strict Excel and text date normalization that never guesses a year."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Optional, Tuple

from .models import Cell
from .styles import is_date_format

DATE_PATTERNS = (
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), "%Y%m%d"),
    (re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$"), None),
)


def _validated_date(year: int, month: int, day: int) -> Optional[str]:
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def parse_date_text(value: object) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    compact = DATE_PATTERNS[0][0].match(text)
    if compact:
        return _validated_date(int(compact.group(1)), int(compact.group(2)), int(compact.group(3)))
    separated = DATE_PATTERNS[1][0].match(text)
    if separated:
        return _validated_date(int(separated.group(1)), int(separated.group(2)), int(separated.group(3)))
    return None


def parse_excel_date(cell: Optional[Cell], date_1904: bool = False) -> Tuple[Optional[str], str, str]:
    """Return canonical date, source text, and a disposition label."""
    if cell is None:
        return None, "", "empty"
    raw = str(cell.value or "").strip()
    if not raw:
        return None, "", "empty"
    if is_date_format(cell.style.number_format):
        try:
            serial = float(raw)
            epoch = datetime(1904, 1, 1) if date_1904 else datetime(1899, 12, 30)
            return (epoch + timedelta(days=serial)).date().isoformat(), raw, "excel_serial"
        except (TypeError, ValueError, OverflowError):
            pass
    parsed = parse_date_text(raw)
    if parsed:
        return parsed, raw, "normalized_text"
    return None, raw, "preserved_unparsed"


def parse_excel_datetime(cell: Optional[Cell], date_1904: bool = False) -> Tuple[Optional[str], str, str]:
    if cell is None:
        return None, "", "empty"
    raw = str(cell.value or "").strip()
    if not raw:
        return None, "", "empty"
    if is_date_format(cell.style.number_format):
        try:
            serial = float(raw)
            epoch = datetime(1904, 1, 1) if date_1904 else datetime(1899, 12, 30)
            value = epoch + timedelta(days=serial)
            return value.replace(second=0, microsecond=0).isoformat(timespec="minutes"), raw, "excel_serial"
        except (TypeError, ValueError, OverflowError):
            pass
    normalized = raw.replace("/", "-").replace(".", "-")
    try:
        value = datetime.fromisoformat(normalized)
        return value.replace(second=0, microsecond=0).isoformat(timespec="minutes"), raw, "normalized_text"
    except ValueError:
        parsed = parse_date_text(raw)
        if parsed:
            return f"{parsed}T00:00", raw, "normalized_text"
    return None, raw, "preserved_unparsed"
