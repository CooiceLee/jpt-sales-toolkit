"""Input and output contracts for read-only transport suggestions."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, replace


MODES = frozenset({"flight", "drive", "ground_public", "other"})
LEG_KEY_RE = re.compile(r"^[A-Za-z0-9:_>.|-]{1,220}$")


def _coordinate(value, *, low: float, high: float, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite coordinate")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite coordinate") from exc
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{field} is out of range")
    return number


@dataclass(frozen=True)
class LegRequest:
    leg_key: str
    mode: str
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float

    @classmethod
    def create(cls, **values) -> "LegRequest":
        leg_key = str(values.get("leg_key") or "")
        mode = str(values.get("mode") or "")
        if not LEG_KEY_RE.fullmatch(leg_key):
            raise ValueError("leg_key contains unsupported characters")
        if mode not in MODES:
            raise ValueError("unsupported transport mode")
        return cls(
            leg_key=leg_key,
            mode=mode,
            from_lat=_coordinate(values.get("from_lat"), low=-90, high=90, field="from_lat"),
            from_lng=_coordinate(values.get("from_lng"), low=-180, high=180, field="from_lng"),
            to_lat=_coordinate(values.get("to_lat"), low=-90, high=90, field="to_lat"),
            to_lng=_coordinate(values.get("to_lng"), low=-180, high=180, field="to_lng"),
        )

    @property
    def cache_key(self) -> str:
        values = (self.leg_key, self.mode, self.from_lat, self.from_lng, self.to_lat, self.to_lng)
        return "|".join(str(round(value, 6)) if isinstance(value, float) else value for value in values)


@dataclass(frozen=True)
class TransportSuggestion:
    suggestion_id: str
    leg_key: str
    mode: str
    distance_km: float | None
    time_hours: float | None
    travel_days: int | None
    provider: str
    online: bool
    status: str
    fetched_at: str
    approximate: bool
    confidence: str
    cached: bool
    search_url: str | None
    requires_manual_confirmation: bool = True
    warning: str | None = None
    attribution: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    def from_cache(self) -> "TransportSuggestion":
        return replace(self, cached=True)
