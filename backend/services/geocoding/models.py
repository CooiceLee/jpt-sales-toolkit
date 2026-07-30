"""Provider-neutral geocoding input and output models."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Optional


def _clean(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


@dataclass(frozen=True)
class GeocodeQuery:
    address: str = ""
    city: str = ""
    postal_code: str = ""
    country: str = ""

    @classmethod
    def create(cls, **values) -> "GeocodeQuery":
        return cls(**{key: _clean(values.get(key)) for key in cls.__dataclass_fields__})

    @property
    def text(self) -> str:
        return ", ".join(
            part for part in (self.address, self.postal_code, self.city, self.country) if part
        )

    @property
    def cache_key(self) -> str:
        normalized = "|".join(
            part.casefold() for part in (self.address, self.city, self.postal_code, self.country)
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GeocodeCandidate:
    lat: float
    lng: float
    normalized_address: str
    confidence: str
    place_type: str
    provider: str
    provider_reference: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GeocodeSearchResult:
    query: GeocodeQuery
    candidates: list[GeocodeCandidate]
    provider: str
    cached: bool = False

    def as_dict(self) -> dict:
        return {
            "query": self.query.as_dict(),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "provider": self.provider,
            "cached": self.cached,
        }
