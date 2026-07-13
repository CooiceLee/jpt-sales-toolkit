"""
Shared review formatting and parsing helpers.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Optional


def num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def md_cell(value) -> str:
    return str(value or "-").replace("|", "\\|").replace("\n", " ")


def csv_cell(value):
    """Escape spreadsheet formulas while leaving csv.writer to handle CSV syntax."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    stripped = text.lstrip()
    if stripped and stripped[0] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def finite_float(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def clean_stay_days(value) -> int:
    try:
        parsed = int(value or 1)
    except (TypeError, ValueError):
        return 1
    return max(1, min(parsed, 30))


def parse_holiday_dates(value) -> tuple[list[str], list[str]]:
    if not value:
        return [], []
    raw_items = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            raw_items = decoded if isinstance(decoded, list) else [value]
        except json.JSONDecodeError:
            raw_items = value.replace("\n", ",").split(",")
    if not isinstance(raw_items, list):
        raw_items = [raw_items]

    dates = set()
    invalid = []
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        parsed = parse_date(text)
        if parsed:
            dates.add(parsed.isoformat())
        else:
            invalid.append(text)
    return sorted(dates), invalid
