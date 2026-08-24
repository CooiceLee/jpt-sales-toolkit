"""Validation and compatibility rules for Trip Planner route legs."""

from __future__ import annotations

import json
import math
from datetime import datetime
CANONICAL_MODES = ("flight", "drive", "ground_public", "other")
DEFAULT_PRIORITY = ("flight", "drive", "ground_public")
OVERRIDE_FIELDS = {
    "selected_mode",
    "mode_locked",
    "manual_distance_km",
    "manual_time_hours",
    "manual_travel_days",
    "manual_travel_half_days",
    "notes",
}

def normalize_priority(value, legacy_mode: str | None = None) -> list[str]:
    if value is None:
        if legacy_mode in CANONICAL_MODES:
            return [legacy_mode]
        return list(DEFAULT_PRIORITY)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("transport_mode_priority must be a JSON array") from exc
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("transport_mode_priority must be a non-empty list")
    result = [str(item) for item in value]
    if len(result) != len(set(result)):
        raise ValueError("transport_mode_priority cannot contain duplicates")
    invalid = [item for item in result if item not in CANONICAL_MODES]
    if invalid:
        raise ValueError("Unsupported transport mode: " + ", ".join(invalid))
    return result
def validate_route_order_mode(value) -> str:
    mode = value or "auto"
    if mode not in {"auto", "manual"}:
        raise ValueError("route_order_mode must be auto or manual")
    return mode
def validate_stop_order(stop_order, active_ids: list[str]) -> list[str] | None:
    if stop_order is None:
        return None
    if not isinstance(stop_order, list):
        raise ValueError("stop_order must be a list")
    if len(stop_order) != len(set(stop_order)):
        raise ValueError("stop_order cannot contain duplicate stop IDs")
    if set(stop_order) != set(active_ids) or len(stop_order) != len(active_ids):
        raise ValueError("stop_order must contain every active stop exactly once")
    return stop_order
def _non_negative(value, field: str, integer: bool = False):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative number")
    try:
        number = int(value) if integer else float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a non-negative number") from exc
    if not math.isfinite(float(number)) or number < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return number


def normalize_overrides(raw, valid_keys: set[str], locked: dict[str, dict]) -> dict[str, dict]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("leg_overrides must be keyed by leg_key")
    unknown_keys = set(raw) - valid_keys
    if unknown_keys:
        raise ValueError("Unknown leg override: " + ", ".join(sorted(unknown_keys)))
    result = {}
    for key in valid_keys:
        incoming = raw.get(key)
        if incoming is not None and not isinstance(incoming, dict):
            raise ValueError(f"leg_overrides[{key}] must be an object")
        value = dict(locked.get(key) or {})
        if incoming is not None:
            unknown_fields = set(incoming) - OVERRIDE_FIELDS
            if unknown_fields:
                raise ValueError(f"Unknown fields in leg_overrides[{key}]")
            value.update(incoming)
        if not value:
            continue
        mode = value.get("selected_mode")
        if mode is not None and mode not in CANONICAL_MODES:
            raise ValueError(f"Unsupported selected_mode for leg {key}")
        value["mode_locked"] = bool(value.get("mode_locked", False))
        for field in ("manual_distance_km", "manual_time_hours"):
            value[field] = _non_negative(value.get(field), field)
        value["manual_travel_days"] = _non_negative(
            value.get("manual_travel_days"), "manual_travel_days", integer=True
        )
        value["manual_travel_half_days"] = _non_negative(
            value.get("manual_travel_half_days"),
            "manual_travel_half_days",
            integer=True,
        )
        if (
            value["manual_travel_half_days"] is not None
            and value["manual_travel_half_days"] > 60
        ):
            raise ValueError("manual_travel_half_days must be at most 60")
        if mode == "other" and not (
            (value.get("manual_time_hours") or 0) > 0
            or value.get("manual_travel_half_days") is not None
            or (value.get("manual_travel_days") or 0) > 0
        ):
            raise ValueError(f"Leg {key} using other requires manual time hours or travel days")
        result[key] = value
    return result


def validate_time_windows(values: dict) -> None:
    for prefix in ("departure", "return"):
        start = values.get(f"{prefix}_window_start")
        end = values.get(f"{prefix}_window_end")
        parsed = []
        for name, value in (("start", start), ("end", end)):
            if not value:
                parsed.append(None)
                continue
            try:
                parsed.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
            except ValueError as exc:
                raise ValueError(f"{prefix}_window_{name} must be ISO date/time") from exc
        if all(parsed):
            if (parsed[0].tzinfo is None) != (parsed[1].tzinfo is None):
                raise ValueError(f"{prefix} window must use a consistent timezone")
            if parsed[1] < parsed[0]:
                raise ValueError(f"{prefix}_window_end cannot be before {prefix}_window_start")
