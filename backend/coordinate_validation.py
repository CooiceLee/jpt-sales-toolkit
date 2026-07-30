"""Shared customer-coordinate validation for every persistence path."""

from __future__ import annotations

import math
from typing import Any, Mapping


class CoordinateValidationError(ValueError):
    """Raised when a supplied latitude or longitude cannot be persisted."""


BOUNDS = {
    "lat": (-90.0, 90.0, "Latitude"),
    "lng": (-180.0, 180.0, "Longitude"),
}


def validated_coordinate_payload(payload: Mapping[str, Any]) -> dict:
    """Return a copy with finite, in-range coordinate values normalized to floats."""
    result = dict(payload)
    for field, (minimum, maximum, label) in BOUNDS.items():
        if field not in result or result[field] is None:
            continue
        value = result[field]
        if isinstance(value, bool):
            raise CoordinateValidationError(f"{label} must be a number")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise CoordinateValidationError(f"{label} must be a number") from exc
        if not math.isfinite(number) or number < minimum or number > maximum:
            raise CoordinateValidationError(
                f"{label} must be between {minimum:g} and {maximum:g}"
            )
        result[field] = number
    return result


def valid_coordinate_pair(lat: Any, lng: Any) -> bool:
    """Return whether both stored values form one finite, in-range coordinate pair."""
    if lat is None or lng is None:
        return False
    try:
        validated_coordinate_payload({"lat": lat, "lng": lng})
    except CoordinateValidationError:
        return False
    return True
